# Copyright (c) 2021 Graphcore Ltd. All rights reserved.
#
# This directory contains derived work from the following: Keras simple MNIST
# convnet example:
# https://github.com/keras-team/keras-io/blob/master/examples/vision/mnist_convnet.py
# Copyright holder unknown (author: François Chollet 2015)
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy of the
# License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#
# This file has been modified by Graphcore Ltd.
import tensorflow.keras as keras
import numpy as np

# Store class and shape information.
num_classes = 10
input_shape = (28, 28, 1)
batch_size = 64


def load_data():
    # Load the MNIST dataset from keras.datasets
    (x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()

    # Normalize the images.
    x_train = x_train.astype("float32") / 255
    x_test = x_test.astype("float32") / 255

    # When dealing with images, we usually want an explicit channel dimension,
    # even when it is 1.
    # Each sample thus has a shape of (28, 28, 1).
    x_train = np.expand_dims(x_train, -1)
    x_test = np.expand_dims(x_test, -1)

    # Finally, convert class assignments to a binary class matrix.
    # Each row can be seen as a rank-1 "one-hot" tensor.
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    return (x_train, y_train), (x_test, y_test)


def model_fn():
    # Input layer - "entry point" / "source vertex".
    input_layer = keras.Input(shape=input_shape)

    # Add layers to the graph.
    x = keras.layers.Conv2D(32, kernel_size=(3, 3), activation="relu")(input_layer)
    x = keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    x = keras.layers.Conv2D(64, kernel_size=(3, 3), activation="relu")(x)
    x = keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    x = keras.layers.Flatten()(x)
    x = keras.layers.Dropout(0.5)(x)
    x = keras.layers.Dense(num_classes, activation="softmax")(x)

    return input_layer, x


(x_train, y_train), (x_test, y_test) = load_data()

print('Keras MNIST example, running on CPU')
# Model.__init__ takes two required arguments, inputs and outputs.
model = keras.Model(*model_fn())

# Compile our model with Stochastic Gradient Descent as an optimizer
# and Categorical Cross Entropy as a loss.
model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"])
model.summary()

print('\nTraining')
model.fit(x_train, y_train, epochs=3, batch_size=batch_size)

print('\nEvaluation')
model.evaluate(x_test, y_test, batch_size=batch_size)

from tensorflow.python import ipu


def make_divisible(number, divisor):
    return number - number % divisor


(x_train, y_train), (x_test, y_test) = load_data()

train_data_len = x_train.shape[0]
train_data_len = make_divisible(train_data_len, batch_size)
x_train, y_train = x_train[:train_data_len], y_train[:train_data_len]

test_data_len = x_test.shape[0]
test_data_len = make_divisible(test_data_len, batch_size)
x_test, y_test = x_test[:test_data_len], y_test[:test_data_len]

ipu_config = ipu.config.IPUConfig()
ipu_config.auto_select_ipus = 1
ipu_config.configure_ipu_system()

strategy = ipu.ipu_strategy.IPUStrategy()

print('Keras MNIST example, running on IPU')
with strategy.scope():
    # Model.__init__ takes two required arguments, inputs and outputs.
    model = keras.Model(*model_fn())

    # Compile our model with Stochastic Gradient Descent as an optimizer
    # and Categorical Cross Entropy as a loss.
    model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"])
    model.summary()

    print('\nTraining')
    model.fit(x_train, y_train, epochs=3, batch_size=batch_size)

    print('\nEvaluation')
    model.evaluate(x_test, y_test, batch_size=batch_size)

(x_train, y_train), (x_test, y_test) = load_data()

train_data_len = x_train.shape[0]
train_steps_per_execution = train_data_len // batch_size
train_data_len = make_divisible(train_data_len, train_steps_per_execution * batch_size)
x_train, y_train = x_train[:train_data_len], y_train[:train_data_len]

test_data_len = x_test.shape[0]
test_steps_per_execution = test_data_len // batch_size
test_data_len = make_divisible(test_data_len, test_steps_per_execution * batch_size)
x_test, y_test = x_test[:test_data_len], y_test[:test_data_len]

print('Keras MNIST example, running on IPU with steps_per_execution')
with strategy.scope():
    # Model.__init__ takes two required arguments, inputs and outputs.
    model = keras.Model(*model_fn())

    # Compile our model with Stochastic Gradient Descent as an optimizer
    # and Categorical Cross Entropy as a loss.
    model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"],
                  steps_per_execution=train_steps_per_execution)
    model.summary()

    print('\nTraining')
    model.fit(x_train, y_train, epochs=3, batch_size=64)

    print('\nEvaluation')
    model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"],
                  steps_per_execution=test_steps_per_execution)
    model.evaluate(x_test, y_test, batch_size=batch_size)

num_ipus = num_replicas = 2

(x_train, y_train), (x_test, y_test) = load_data()

# Adjust dataset lengths to be divisible by the batch size
train_data_len = x_train.shape[0]
train_steps_per_execution = train_data_len // (batch_size * num_replicas)
# `steps_per_execution` needs to be divisible by the number of replicas
train_steps_per_execution = make_divisible(train_steps_per_execution, num_replicas)
train_data_len = make_divisible(train_data_len, train_steps_per_execution * batch_size)
x_train, y_train = x_train[:train_data_len], y_train[:train_data_len]

test_data_len = x_test.shape[0]
test_steps_per_execution = test_data_len // (batch_size * num_replicas)
# `steps_per_execution` needs to be divisible by the number of replicas
test_steps_per_execution = make_divisible(test_steps_per_execution, num_replicas)
test_data_len = make_divisible(test_data_len, test_steps_per_execution * batch_size)
x_test, y_test = x_test[:test_data_len], y_test[:test_data_len]

ipu_config = ipu.config.IPUConfig()
ipu_config.auto_select_ipus = num_ipus
ipu_config.configure_ipu_system()

print('Keras MNIST example, running on IPU with replication')
with strategy.scope():
    # Model.__init__ takes two required arguments, inputs and outputs.
    model = keras.Model(*model_fn())

    # Compile our model with Stochastic Gradient Descent as an optimizer
    # and Categorical Cross Entropy as a loss.
    model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"],
                  steps_per_execution=train_steps_per_execution)
    model.summary()

    print('\nTraining')
    model.fit(x_train, y_train, epochs=3, batch_size=64)

    print('\nEvaluation')
    model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"],
                  steps_per_execution=test_steps_per_execution)
    model.evaluate(x_test, y_test, batch_size=batch_size)

num_ipus = 2
num_replicas = num_ipus // 2
gradient_accumulation_steps_per_replica = 8

(x_train, y_train), (x_test, y_test) = load_data()

total_gradient_accumulation_steps = gradient_accumulation_steps_per_replica * num_replicas

# Adjust dataset lengths to be divisible by the batch size
train_data_len = x_train.shape[0]
train_steps_per_execution = train_data_len // (batch_size * num_replicas)
# `steps_per_execution` needs to be divisible by `total_gradient_accumulation_steps`
train_steps_per_execution = make_divisible(train_steps_per_execution, total_gradient_accumulation_steps)
train_data_len = make_divisible(train_data_len, train_steps_per_execution * batch_size)
x_train, y_train = x_train[:train_data_len], y_train[:train_data_len]

test_data_len = x_test.shape[0]
test_steps_per_execution = test_data_len // (batch_size * num_replicas)
# `steps_per_execution` needs to be divisible by `total_gradient_accumulation_steps`
test_steps_per_execution = make_divisible(test_steps_per_execution, total_gradient_accumulation_steps)
test_data_len = make_divisible(test_data_len, test_steps_per_execution * batch_size)
x_test, y_test = x_test[:test_data_len], y_test[:test_data_len]


def model_fn():
    # Input layer - "entry point" / "source vertex".
    input_layer = keras.Input(shape=input_shape)

    # Add graph nodes for the first pipeline stage.
    with ipu.keras.PipelineStage(0):
        x = keras.layers.Conv2D(32, kernel_size=(3, 3), activation="relu")(input_layer)
        x = keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
        x = keras.layers.Conv2D(64, kernel_size=(3, 3), activation="relu")(x)

    # Add graph nodes for the second pipeline stage.
    with ipu.keras.PipelineStage(1):
        x = keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
        x = keras.layers.Flatten()(x)
        x = keras.layers.Dropout(0.5)(x)
        x = keras.layers.Dense(num_classes, activation="softmax")(x)

    return input_layer, x


print('Keras MNIST example, running on IPU with pipelining')
with strategy.scope():
    # Model.__init__ takes two required arguments, inputs and outputs.
    model = keras.Model(*model_fn())

    model.set_pipelining_options(
        gradient_accumulation_steps_per_replica=gradient_accumulation_steps_per_replica,
        pipeline_schedule=ipu.ops.pipelining_ops.PipelineSchedule.Grouped
    )

    # Compile our model with Stochastic Gradient Descent as an optimizer
    # and Categorical Cross Entropy as a loss.
    model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"],
                  steps_per_execution=train_steps_per_execution)
    model.summary()

    print('\nTraining')
    model.fit(x_train, y_train, epochs=3, batch_size=batch_size)

    print('\nEvaluation')
    model.compile('sgd', 'categorical_crossentropy', metrics=["accuracy"],
                  steps_per_execution=test_steps_per_execution)
    model.evaluate(x_test, y_test, batch_size=batch_size)
