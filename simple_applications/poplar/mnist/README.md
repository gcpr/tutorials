# Basic Model Demo for MNIST dataset

This demo shows how to use one IPU for a simple Poplar model with MNIST dataset.
It contains a complete training program that performs a logistic
regression on the MNIST data set, using gradient descent.

## File structure

* `regression_demo.cpp` The main script containing the model.
* `mnist.h` and `mnist.cpp` Helper files to iterate over the MNIST dataset.
* `get_data.sh` A script to download the MNIST dataset.
* `README.rst` This file.

## How to use this application
1) Prepare the Poplar environment.

   Install the Poplar SDK following the Getting Started guide for your IPU system.
   Make sure to run the `enable.sh` script for Poplar.

2) Run the ``get_data.sh`` script to download the MNIST data.

        ./get_data.sh

3) Build the code with the Makefile provided:

        make

4) Train and test the model:

        ./regression-demo [-IPU] [number of epochs] [proportion of images to use]

Copyright (c) 2018 Graphcore Ltd. All rights reserved.
