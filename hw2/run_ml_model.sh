#!/bin/bash
# run_ml_model.sh
# Run the machine learning model for CS 536 Assignment 2, Part 3.
# After running the run_experiment.sh script to collect data,
# this script will process the data and train the ML model.
python3 ML_model.py --csv ./results/q2_goodput_samples.csv --plots plots/ --models models/

# the generated plots and models will be saved in the specified directories.