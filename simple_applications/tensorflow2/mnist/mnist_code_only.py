# Copyright (c) 2020 Graphcore Ltd. All rights reserved.
import tensorflow as tf

from tensorflow import keras
from tensorflow.python import ipu

if tf.__version__[0] != '2':
    raise ImportError("TensorFlow 2 is required for this example")


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


def create_model():
    model = keras.Sequential([
        keras.layers.Flatten(),
        keras.layers.Dense(128, activation='relu'),
        keras.layers.Dense(10, activation='softmax')])
    return model


# Configure the IPU system
cfg = ipu.config.IPUConfig()
cfg.auto_select_ipus = 1
cfg.configure_ipu_system()

# Create an IPU distribution strategy.
strategy = ipu.ipu_strategy.IPUStrategy()

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
