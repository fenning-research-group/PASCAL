# Readme for PASCAL

# Install guide
## PASCAL
- clone main repo
- On Windows: run the following command in a Powershell prompt and enter "y" when prompted: `winget install Microsoft.VisualStudio.2022.BuildTools --force --override "--wait --passive --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.VC.CMake.Project --add Microsoft.VisualStudio.Component.TestTools.BuildTools --add Microsoft.VisualStudio.Component.VC.ASAN"`
- cd to directory with `setup.py`, run `pip install .`

## Analysis models
copy following files into `frgpascal\analysis\assets`:
- `Brightfield_SampleChecker_Model.h5` from Jack's staff folder on FRG team drive
