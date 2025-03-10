# Copyright (c) 2020 Graphcore Ltd. All rights reserved.
from tqdm import tqdm
import torch
import torch.nn as nn
import torchvision
import poptorch
import torch.optim as optim

learning_rate = 0.03

epochs = 10

batch_size = 8

test_batch_size = 80

import argparse
parser = argparse.ArgumentParser(description='MNIST training in PopTorch')
parser.add_argument('--batch-size', type=int, default=8, help='batch size for training (default: 8)')
parser.add_argument('--device-iterations', type=int, default=50, help='device iteration (default:50)')
parser.add_argument('--test-batch-size', type=int, default=80, help='batch size for testing (default: 80)')
parser.add_argument('--epochs', type=int, default=10, help='number of epochs to train (default: 10)')
parser.add_argument('--lr', type=float, default=0.05, help='learning rate (default: 0.05)')
opts = parser.parse_args()

learning_rate = opts.lr
epochs = opts.epochs
batch_size = opts.batch_size
test_batch_size = opts.test_batch_size
device_iterations = opts.device_iterations

device_iterations = 50

local_dataset_path = '~/.torch/datasets'

transform_mnist = torchvision.transforms.Compose(
    [
        torchvision.transforms.ToTensor(),
        torchvision.transforms.Normalize((0.1307, ), (0.3081, ))
    ]
)

training_dataset = torchvision.datasets.MNIST(
    local_dataset_path,
    train=True,
    download=True,
    transform=transform_mnist
)

test_dataset = torchvision.datasets.MNIST(
    local_dataset_path,
    train=False,
    download=True,
    transform=transform_mnist
)

training_opts = poptorch.Options()
training_opts = training_opts.deviceIterations(device_iterations)

training_data = poptorch.DataLoader(
    options=training_opts,
    dataset=training_dataset,
    batch_size=batch_size,
    shuffle=True,
    drop_last=True
)

test_data = poptorch.DataLoader(
    options=poptorch.Options(),
    dataset=test_dataset,
    batch_size=test_batch_size,
    shuffle=True,
    drop_last=True
)


class Block(nn.Module):
    def __init__(self, in_channels, num_filters, kernel_size, pool_size):
        super(Block, self).__init__()
        self.conv = nn.Conv2d(in_channels,
                              num_filters,
                              kernel_size=kernel_size)
        self.pool = nn.MaxPool2d(kernel_size=pool_size)
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.conv(x)
        x = self.pool(x)
        x = self.relu(x)
        return x


class Network(nn.Module):
    def __init__(self):
        super(Network, self).__init__()
        self.layer1 = Block(1, 32, 3, 2)
        self.layer2 = Block(32, 64, 3, 2)
        self.layer3 = nn.Linear(1600, 128)
        self.layer3_act = nn.ReLU()
        self.layer3_dropout = torch.nn.Dropout(0.5)
        self.layer4 = nn.Linear(128, 10)
        self.softmax = nn.Softmax(1)

    def forward(self, x):
        x = self.layer1(x)
        x = self.layer2(x)
        # Flatten layer
        x = x.view(-1, 1600)
        x = self.layer3_act(self.layer3(x))
        x = self.layer4(self.layer3_dropout(x))
        x = self.softmax(x)
        return x


class TrainingModelWithLoss(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.loss = torch.nn.CrossEntropyLoss()

    def forward(self, args, labels=None):
        output = self.model(args)
        if labels is None:
            return output
        else:
            loss = self.loss(output, labels)
            return output, loss


model = Network()
model_with_loss = TrainingModelWithLoss(model)

training_opts = poptorch.Options().deviceIterations(device_iterations)

training_opts = training_opts.outputMode(poptorch.OutputMode.All)

print(model_with_loss)

training_model = poptorch.trainingModel(
    model_with_loss,
    training_opts,
    optimizer=optim.SGD(model.parameters(), lr=learning_rate)
)

from metrics import accuracy

nr_steps = len(training_data)

for epoch in tqdm(range(1, epochs + 1), leave=True, desc="Epochs", total=epochs):
    with tqdm(training_data, total=nr_steps, leave=False) as bar:
        for data, labels in bar:
            preds, losses = training_model(data, labels)

            mean_loss = torch.mean(losses).item()

            acc = accuracy(preds, labels)
            bar.set_description(
                "Loss: {:0.4f} | Accuracy: {:05.2F}% ".format(mean_loss, acc)
            )

training_model.detachFromDevice()

inference_model = poptorch.inferenceModel(model)

nr_steps = len(test_data)
sum_acc = 0.0
with tqdm(test_data, total=nr_steps, leave=False) as bar:
    for data, labels in bar:
        output = inference_model(data)
        sum_acc += accuracy(output, labels)

print("Accuracy on test set: {:0.2f}%".format(sum_acc / len(test_data)))
