# Thorlabs TSI SDK Python Wrapper

This is the python wrapper for the thorlabs tsi sdk. It uses the ctypes library to wrap around the native thorlabs TSI sdk DLLs. The python wrapper does NOT contain the DLLs, the user will need to set up their environment so their application can find the DLLs. A couple ways this can be done is by adding the DLLs to the working directory of the program or adding the DLLs directory to the PATH environment variable (either manually or in python at runtime).

## Virtual Environment

This library expects the developer to create a virtual environment (called __env__) in the <code>NativePythonWrapper\python</code> folder. This is used when developing / debugging the SDK and for building the final package. The preferred virtual environment creator is __virtualenv__. Here are the steps to creating a virtual environment:
* Make sure you have __Python 3.7__ or higher installed, as well as the __virtualenv__ package: <code>python.exe -m pip install virtualenv</code>
* From the <code>NativePythonWrapper\python</code> folder, create a virtual environment called __env__: <code>python.exe -m virtualenv env</code>
* Install all the required libraries to this new virtual environment using the __Requirements.txt__ in the <code>NativePythonWrapper\python</code> folder: <code>env\Scripts\python.exe -m pip install -r Requirements.txt</code>

Certain batch files may require this python environment to do some operations, such as building the documentation using Sphinx. 

This only has to be done once when the repository is cloned. If you need to add a package to the virtual environment, include it in the __Requirements.txt__ and make a note for developers to update their environments (<code>env\Scripts\python.exe -m pip install -r Requirements.txt</code>).