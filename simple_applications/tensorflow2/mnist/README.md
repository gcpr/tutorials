# Training a simple TensorFlow 2 model on MNIST with an IPU

This tutorial shows how to train a simple model using the MNIST numerical
dataset on a single IPU. The dataset consists of 60,000 images of handwritten
digits (0-9) that must be classified according to which digit they represent.

We will do the following steps in order:
1. Load and pre-process the MNIST dataset from Keras.
2. Define a simple model.
3. Configure the IPU system
4. Train the model on the IPU.

## 1. Preparing your environment
In order to run this tutorial on the IPU you will need:
- A Poplar SDK environment enabled (see the [Getting Started](https://docs.graphcore.ai/en/latest/getting-started.html) guide for your IPU system).
- TensorFlow 2 set up for the IPU (see the [Setup Instructions](https://docs.graphcore.ai/projects/ipu-pod-getting-started/en/latest/installation.html#setting-up-tensorflow-for-the-ipu))

To run the Jupyter notebook version of this tutorial:
1. Enable a Poplar SDK environment
2. In the same environment, install the Jupyter notebook server: `python -m pip install notebook`
3. Launch a Jupyter Server on a specific port: `jupyter-notebook --no-browser --port <port number>`
4. Connect via SSH to your remote machine, forwarding your chosen port: `ssh -NL <port number>:localhost:<port number> <your username>@<remote machine>`

For more details about this process, or if you need troubleshooting, see our [guide on using IPUs from Jupyter notebooks](../../../tutorials/standard_tools/using_jupyter/).

## 2. Import the necessary libraries

First of all, we need to import APIs that will be used in the example.


```python
import tensorflow as tf

from tensorflow import keras
from tensorflow.python import ipu

if tf.__version__[0] != '2':
    raise ImportError("TensorFlow 2 is required for this example")
```

For the `ipu` module to function properly, we must import it directly rather
than accessing it through the top-level TensorFlow module.

## 3. Prepare the dataset

We can access the MNIST dataset through keras:


```python
def create_dataset():
    mnist = keras.datasets.mnist

    (x_train, y_train), _ = mnist.load_data()
    x_train = x_train / 255.0

    train_ds = tf.data.Dataset.from_tensor_slices(
        (x_train, y_train)).shuffle(10000).batch(32, drop_remainder=True)
    train_ds = train_ds.map(
        lambda d, l: (tf.cast(d, tf.float32), tf.cast(l, tf.float32)))

    # Create a looped version of the dataset
    return train_ds.repeat()
```

We normalise the dataset by dividing each element of `x_train` (pixel values)
by 255. This results in smaller numbers that range from 0 to 1, which leads
to faster computation.

Some extra care must be taken when preparing a dataset for training a Keras
model on the IPU. The Poplar software stack does not support using tensors
with shapes which are not known when the model is compiled.

To address this we use the `.batch()` method to make sure the sizes of our
dataset are divisible by the batch size. The `.batch()` method takes the batch
size as an argument and has the option to discard the remaining elements after
the dataset is divided (`drop_remainder`). This option must be
set to true in order to use the dataset with Keras model on the IPU.

## 4. Define the model

Next, we define our model using the Keras Sequential API.


```python
def create_model():
    model = keras.Sequential([
        keras.layers.Flatten(),
        keras.layers.Dense(128, activation='relu'),
        keras.layers.Dense(10, activation='softmax')])
    return model
```

## 5. Add IPU configuration

To use the IPU, we must create an IPU configuration.
We can use `cfg.auto_select_ipus = 1` to automatically select one IPU:


```python
# Configure the IPU system
cfg = ipu.config.IPUConfig()
cfg.auto_select_ipus = 1
cfg.configure_ipu_system()
```

This is all we need to get a small model up and running, though a full list of
configuration options is available in the [API documentation](https://docs.graphcore.ai/projects/tensorflow-user-guide/en/latest/tensorflow/api.html#tensorflow.python.ipu.config.IPUConfig).

If you're interested in learning how to optimally use models that require
multiple IPUs (for example due to their size), see the section on pipelining
from our documentation on [model parallelism](https://docs.graphcore.ai/projects/tf-model-parallelism/en/latest/model.html).

> To see how this process can be implemented, head over to the pipelining section of our [TensorFlow 2 Keras tutorial](../../tutorials/tensorflow2/keras).

## 6. Specify IPU strategy

Next, add the following code after the configuration:


```python
# Create an IPU distribution strategy.
strategy = ipu.ipu_strategy.IPUStrategy()
```

The `tf.distribute.Strategy` is an API to distribute training across multiple
devices. `IPUStrategy` is a subclass which targets a system with one or more
IPUs attached. For a multi-system configuration, the
[PopDistStrategy](https://docs.graphcore.ai/projects/tensorflow-user-guide/en/latest/tensorflow/api.html#tensorflow.python.ipu.horovod.popdist_strategy.PopDistStrategy)
should be used, in conjunction with our PopDist library.

> To see an example of how to distribute training over multiple instances with PopDist, head over to our [TensorFlow 2 PopDist example](../../feature_examples/tensorflow2/popdist).

## 7. Wrap the model within the IPU strategy scope

Creating variables within the scope of the `IPUStrategy` will ensure that they
are placed on the IPU, but the initialization for the variables will be
performed on the CPU device. To do this, we create a `strategy.scope()` context
manager and put all the model code inside of it:


```python
with strategy.scope():
    # Create an instance of the model.
    model = create_model()

    # Get the training dataset.
    ds = create_dataset()

    # Train the model.
    model.compile(loss = keras.losses.SparseCategoricalCrossentropy(),
                  optimizer = keras.optimizers.SGD(),
                  steps_per_execution=100)
    model.fit(ds, steps_per_epoch=2000, epochs=4)
```

The `steps_per_execution` argument in `model.compile()` sets the
number of batches processed in each execution of the underlying IPU program.
Not specifying this argument causes the program that runs on the IPU to only
process a single batch per execution, which means more time is wasted waiting
for I/O instead of using the IPU.

Another way to speed up the training of a model is through replication. This
process involves copying the model on each of multiple IPUs, updating the
parameters of the model on all IPUs after each forward and backward pass. To
learn more about this process, head over to our documentation on
[graph replication](https://docs.graphcore.ai/projects/memory-performance-optimisation/en/latest/main.html?highlight=replication#graph-replication).

> To see how this process can be implemented, take a look at the Replication section of our [TensorFlow 2 Keras tutorial](../../tutorials/tensorflow2/keras).

## Other useful resources

- [TensorFlow Docs](https://docs.graphcore.ai/en/latest/software.html#tensorflow): all Graphcore documentation specifically relating to TensorFlow.

- [IPU TensorFlow 2 Code Examples](https://github.com/graphcore/examples/tree/master/code_examples/tensorflow2): examples of different use cases of TensorFlow 2 on the IPU.
