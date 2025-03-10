# PyTorch (PopTorch) MNIST Training Demo
This example demonstrates how to train a neural network for classification on the MNIST dataset using PopTorch.
To learn more about PopTorch, see our [PyTorch for the IPU: User Guide](https://docs.graphcore.ai/projects/poptorch-user-guide/en/latest/index.html).

## How to use this demo
Requirements:
- A Poplar SDK environment enabled, with PopTorch installed (see the [Getting Started](https://docs.graphcore.ai/en/latest/getting-started.html) guide for your IPU system)
- Python packages installed with `python -m pip install -r requirements.txt`

To run the Jupyter notebook version of this tutorial:
1. Enable a Poplar SDK environment and install required packages with `python -m pip install -r requirements.txt`
2. In the same environment, install the Jupyter notebook server: `python -m pip install notebook`
3. Launch a Jupyter Server on a specific port: `jupyter-notebook --no-browser --port <port number>`
4. Connect via SSH to your remote machine, forwarding your chosen port:
`ssh -NL <port number>:localhost:<port number> <your username>@<remote machine>`

For more details about this process, or if you need troubleshooting, see our [guide on using IPUs from Jupyter notebooks](../../../tutorials/standard_tools/using_jupyter/README.md).

## Training a PopTorch model for MNIST classification

### Importing required libraries


```python
from tqdm import tqdm
import torch
import torch.nn as nn
import torchvision
import poptorch
import torch.optim as optim
```

### Setting hyperparameters


```python
learning_rate = 0.03

epochs = 10

batch_size = 8

test_batch_size = 80
```

Device iteration defines the number of iterations the device should
run over the data before returning to the user.
This is equivalent to running the IPU in a loop over that the specified
number of iterations, with a new batch of data each time. However, increasing
deviceIterations is more efficient because the loop runs on the IPU directly.


```python
device_iterations = 50
```

### Preparing the data
We use the `torchvision` package to get the MNIST dataset and we create two data loaders: one for training, one for testing.
Source: [The MNIST Database](http://yann.lecun.com/exdb/mnist/).


```python
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
```

We use the [data loader provided by PopTorch](https://docs.graphcore.ai/projects/poptorch-user-guide/en/latest/pytorch_to_poptorch.html#preparing-your-data).
More information about the use of `poptorch.Dataloader` can be found in [PopTorch tutorial on efficient data loading](../tut2_efficient_data_loading)

A `poptorch.Options()` instance contains a set of default hyperparameters and options for the IPU.
This is used by the model and the PopTorch `DataLoader`.
To accelerate the training here, we change the default value of
[deviceIterations](https://docs.graphcore.ai/projects/poptorch-user-guide/en/latest/batching.html?highlight=deviceiteration#poptorch-options-deviceiterations)
to 50.
With that setting the data loader will pick 50 batches of data per step.


```python
training_opts = poptorch.Options()
training_opts = training_opts.deviceIterations(device_iterations)

training_data = poptorch.DataLoader(
    options=training_opts,
    dataset=training_dataset,
    batch_size=batch_size,
    shuffle=True,
    drop_last=True
)
```

For the validation, we choose not to change `deviceIterations`, we will use a default `poptorch.Options()` instance.


```python
test_data = poptorch.DataLoader(
    options=poptorch.Options(),
    dataset=test_dataset,
    batch_size=test_batch_size,
    shuffle=True,
    drop_last=True
)
```

### Defining the model
Let's define our neural network.
This step is similar to what we would do if we were not using an IPU.


```python
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
```

To ensure the loss computation is placed on the IPU, we need to set
it in the `forward()` method of our `torch.nn.Module`.
We define a thin wrapper around the `torch.nn.Module` that will use
the cross-entropy loss function.
This class is creating a custom module to compose the Neural Network and
the Cross Entropy module into one object, which under the hood will invoke
the `__call__` function on `nn.Module` and consequently the `forward` method.


```python
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
```

Let's initialise the neural network from our defined classes.


```python
model = Network()
model_with_loss = TrainingModelWithLoss(model)
```

### From Pytorch to Poptorch

We start by initializing the training `Options` that will be used by the training model.
`deviceIterations` is set as we did for the training `DataLoader`.
With this setting, the training loop on the device will perform 50 iterations before returning control to the host process.
Therefore, from the host point of view, each step will consume 50 batches and perform 50 weight updates.


```python
training_opts = poptorch.Options().deviceIterations(device_iterations)
```

Now let's set the [`OutputMode`](https://docs.graphcore.ai/projects/poptorch-user-guide/en/latest/reference.html#poptorch.OutputMode)
for our training. By default, PopTorch will
return to the host machine only a limited set of information for performance
reasons. This is represented by having `OutputMode.Final` as the default, which
means that only the final batch of the internal training loop is returned to the host.
When inspecting the training performance as it is executing, values like
accuracy or losses will only be returned for that last batch.
We can set this to `OutputMode.All` to be able to present the full information.
This has an impact on the speed of training, due to overhead of transferring
more data to the host machine.


```python
training_opts = training_opts.outputMode(poptorch.OutputMode.All)
```

We can check if the model is assembled correctly by printing the string
representation of the model object.


```python
print(model_with_loss)
```

    TrainingModelWithLoss(
      (model): Network(
        (layer1): Block(
          (conv): Conv2d(1, 32, kernel_size=(3, 3), stride=(1, 1))
          (pool): MaxPool2d(kernel_size=2, stride=2, padding=0, dilation=1, ceil_mode=False)
          (relu): ReLU()
        )
        (layer2): Block(
          (conv): Conv2d(32, 64, kernel_size=(3, 3), stride=(1, 1))
          (pool): MaxPool2d(kernel_size=2, stride=2, padding=0, dilation=1, ceil_mode=False)
          (relu): ReLU()
        )
        (layer3): Linear(in_features=1600, out_features=128, bias=True)
        (layer3_act): ReLU()
        (layer3_dropout): Dropout(p=0.5, inplace=False)
        (layer4): Linear(in_features=128, out_features=10, bias=True)
        (softmax): Softmax(dim=1)
      )
      (loss): CrossEntropyLoss()
    )


Now we apply the model wrapping function, which will perform a shallow copy
of the PyTorch model. To train the model, we will use [SGD](https://docs.graphcore.ai/projects/poptorch-user-guide/en/latest/reference.html#poptorch.optim.SGD),
the Stochastic Gradient Descent with no momentum.
This is also where we pass the `training_opts` defined sooner.


```python
training_model = poptorch.trainingModel(
    model_with_loss,
    training_opts,
    optimizer=optim.SGD(model.parameters(), lr=learning_rate)
)
```

### Training loop
We are ready to start training! However to track the accuracy while training
we need to define one more helper function. During the training, not every
samples prediction is returned for efficiency reasons, so this helper function
will check accuracy for labels where prediction is available. This behavior
is controlled by setting `AnchorMode` in `poptorch.Options()`.


```python
from metrics import accuracy
```

This code will perform the training over the requested amount of epochs
and batches using the configured Graphcore IPUs.
Since we set `device_iterations` to 50 and Poptorch `OutputMode` to `All`,
`losses` contains the losses of the 50 batches processed by the internal loop.
The first call to `training_model` will compile the model for the IPU.


```python
nr_steps = len(training_data)

for epoch in tqdm(range(1, epochs+1), leave=True, desc="Epochs", total=epochs):
    with tqdm(training_data, total=nr_steps, leave=False) as bar:
        for data, labels in bar:
            preds, losses = training_model(data, labels)

            mean_loss = torch.mean(losses).item()

            acc = accuracy(preds, labels)
            bar.set_description(
                "Loss: {:0.4f} | Accuracy: {:05.2F}% ".format(mean_loss, acc)
            )
```

We could also do it separately by calling `training_model.compile()` in the first place.

Now let's release resources so we can reuse them for our validation:


```python
training_model.detachFromDevice()
```

## Evaluating the trained model
Let's check the validation loss on IPU using the trained model. The weights
in `model.parameters()` will be copied from the IPU to the host. The weights
from the trained model will be reused to compile the new inference model.


```python
inference_model = poptorch.inferenceModel(model)
```

Perform validation:


```python
nr_steps = len(test_data)
sum_acc = 0.0
with tqdm(test_data, total=nr_steps, leave=False) as bar:
    for data, labels in bar:
        output = inference_model(data)
        sum_acc += accuracy(output, labels)
```

Finally the accuracy on the test set is:


```python
print("Accuracy on test set: {:0.2f}%".format(sum_acc / len(test_data)))
```

    Accuracy on test set: 98.57%

