# Copyright (c) 2021 Graphcore Ltd. All rights reserved.
# The following code is only necessary to prevent errors when running the source
# file as a script.


def is_interactive():
    import __main__ as main
    return not hasattr(main, '__file__')


if __name__ == "__main__" and not is_interactive():
    print("This tutorial has been designed to run in a Jupyter notebook. "
          "If you would like to run it as a Python script, please "
          "use tuto_data_loading.py instead. This is required due to Python "
          "process spawning issues when using asynchronous data loading, "
          "as detailed in the README.")
    exit(0)

import time
from sys import exit

import poptorch
import torch
import torch.nn as nn

device_iterations = 50
batch_size = 16
replicas = 1
num_workers = 4


class ClassificationModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 5, 3)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(5, 12, 5)
        self.norm = nn.GroupNorm(3, 12)
        self.fc1 = nn.Linear(41772, 100)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(100, 10)
        self.log_softmax = nn.LogSoftmax(dim=0)
        self.loss = nn.NLLLoss()

    def forward(self, x, labels=None):
        x = self.pool(self.relu(self.conv1(x)))
        x = self.norm(self.relu(self.conv2(x)))
        x = torch.flatten(x, start_dim=1)
        x = self.relu(self.fc1(x))
        x = self.log_softmax(self.fc2(x))
        if self.training:
            return x, self.loss(x, labels)
        return x


opts = poptorch.Options()
opts.deviceIterations(device_iterations)
opts.replicationFactor(replicas)

model = ClassificationModel()
model.train()  # Switch the model to training mode
# Models are initialised in training mode by default, so the line above will
# have no effect. Its purpose is to show how the mode can be set explicitly.

training_model = poptorch.trainingModel(
    model,
    opts,
    torch.optim.SGD(model.parameters(), lr=0.001, momentum=0.9))

features = torch.randn([10000, 1, 128, 128])
labels = torch.empty([10000], dtype=torch.long).random_(10)
dataset = torch.utils.data.TensorDataset(features, labels)

training_data = poptorch.DataLoader(
    opts,
    dataset=dataset,
    batch_size=batch_size,
    shuffle=True,
    drop_last=True,
    num_workers=num_workers,
    mode=poptorch.DataLoaderMode.Async
)


class catchtime:
    def __enter__(self):
        self.seconds = time.time()
        return self

    def __exit__(self, type, value, traceback):
        self.seconds = time.time() - self.seconds


steps = len(training_data)
with catchtime() as t:
    for i, (data, labels) in enumerate(training_data):
        a, b = data, labels

print(f"Total execution time: {t.seconds:.2f} s")
items_per_second = (steps * device_iterations * batch_size * replicas) / t.seconds
print(f"DataLoader throughput: {items_per_second:.2f} items/s")

training_data.terminate()

opts = poptorch.Options()
opts.deviceIterations(device_iterations)
opts.replicationFactor(replicas)
opts.enableSyntheticData(True)

training_model = poptorch.trainingModel(
    model,
    opts,
    poptorch.optim.SGD(model.parameters(), lr=0.001, momentum=0.9, use_combined_accum=False)
)
training_data = poptorch.DataLoader(
    opts,
    dataset=dataset,
    batch_size=batch_size,
    shuffle=True,
    drop_last=True,
    num_workers=num_workers,
    mode=poptorch.DataLoaderMode.Async,
    async_options={"early_preload": True}
)
steps = len(training_data)
data_batch, labels_batch = next(iter(training_data))
training_model.compile(data_batch, labels_batch)

print(f"Evaluating: {steps} steps of {device_iterations * batch_size * replicas} items")

# With synthetic data enabled, no data is copied from the host to the IPU,
# so we don't use the dataloader, to prevent influencing the execution
# time and therefore the IPU throughput calculation
with catchtime() as t:
    for _ in range(steps):
        training_model(data_batch, labels_batch)

items_per_second = (steps * device_iterations * batch_size * replicas) / t.seconds
print(f"Total execution time: {t.seconds:.2f} s")
print(f"IPU throughput: {items_per_second:.2f} items/s")

training_data.terminate()


def validate_model_performance(dataset, device_iterations=50,
                               batch_size=16, replicas=4, num_workers=4,
                               synthetic_data=False):
    opts = poptorch.Options()
    opts.deviceIterations(device_iterations)
    opts.replicationFactor(replicas)
    if synthetic_data:
        opts.enableSyntheticData(True)

    training_data = poptorch.DataLoader(opts, dataset=dataset, batch_size=batch_size,
                                        shuffle=True, drop_last=True,
                                        num_workers=num_workers,
                                        mode=poptorch.DataLoaderMode.Async,
                                        async_options={"early_preload": True})
    steps = len(training_data)
    with catchtime() as t:
        for data_batch, labels_batch in training_data:
            pass

    items_per_second = (steps * device_iterations * batch_size * replicas) / t.seconds
    print(f"DataLoader: {items_per_second:.2f} items/s")
    print(f"Dataloader execution time: {t.seconds:.2f} s")

    if synthetic_data:
        # With synthetic data enabled, no data is copied from the host to the IPU, so we don't use
        # the dataloader, to prevent influencing the execution time and therefore the IPU throughput calculation
        with catchtime() as t:
            for _ in range(steps):
                training_model(data_batch, labels_batch)
    else:
        with catchtime() as t:
            for data, labels in training_data:
                training_model(data, labels)

    items_per_second = (steps * device_iterations * batch_size * replicas) / t.seconds
    print(f"IPU throughput: {items_per_second:.2f} items/s")
    print(f"Dataloader with IPU training execution time: {t.seconds:.2f} s")

    training_data.terminate()


validate_model_performance(dataset, batch_size=16, replicas=1,
                           device_iterations=50, num_workers=4,
                           synthetic_data=True)

validate_model_performance(dataset, batch_size=16, replicas=1,
                           device_iterations=50, num_workers=4,
                           synthetic_data=False)

validate_model_performance(dataset, batch_size=16, replicas=4,
                           device_iterations=50, num_workers=4,
                           synthetic_data=True)

validate_model_performance(dataset, batch_size=16, replicas=4,
                           device_iterations=50, num_workers=4,
                           synthetic_data=False)
