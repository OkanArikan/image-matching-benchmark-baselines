#!/bin/bash

MY_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Make sure the workspace is in the python path
export PYTHONPATH="${PYTHONPATH}:${MY_DIR}"

# The python virtual envisonment must exist
if ! [ -f "${MY_DIR}/.venv/bin/activate" ]
then
    python3 -m venv "${MY_DIR}/.venv"

    # Get into the virtual environment
    source "${MY_DIR}/.venv/bin/activate"

    # Update pip3
    pip3 install --upgrade pip setuptools wheel

    # Install the global python pip requirements
    pip3 install -q --upgrade -r "${MY_DIR}/requirements.txt"
else
    source "${MY_DIR}/.venv/bin/activate"    
fi