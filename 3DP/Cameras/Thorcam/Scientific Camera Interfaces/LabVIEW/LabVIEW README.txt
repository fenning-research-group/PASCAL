LabVIEW README

For LabVIEW support for all Thorlabs DCC- and DCU-series cameras, please see the DCx Camera Support folder typically installed at C:\Program Files\Thorlabs\Scientific Imaging\DCx Camera Support.

For LabVIEW support for all Thorlabs Scientific Cameras (340, 1500, 1501, 4070, 8050, 8051, CS2100M-USB, CS235MU, CS235CU, CS505MU, CS505CU, CS505MUP, CS895MU, and CS895CU), please use the .NET camera interface by following these directions:

1. Install ThorCam and the appropriate drivers using the installer CD that came with a camera or download an installer from the appropriate product page at Thorlabs.com.

2. Copy the managed DLLs from

 Scientific Camera Interfaces\SDK\DotNet Toolkit\dlls\Managed_32_lib\*.dll        (for 32-bit LabVIEW)
 or
 Scientific Camera Interfaces\SDK\DotNet Toolkit\dlls\Managed_64_lib\*.dll        (for 64-bit LabVIEW)
 
 to the a folder with your VIs in a subfolder called Library_X86 (for 32-bit LabVIEW) or Library_X64 (for 64-bit LabVIEW).

3. See the following guides found in the Documentation folder (usually C:\Program Files\Thorlabs\Scientific Imaging\Documentation\Scientific Camera Documents):

 TSI_Camera_LabVIEW_Interface_Guide.pdf
 TSI_Camera_DotNET-LabVIEW-MATLAB_Programming_Guide.chm
 