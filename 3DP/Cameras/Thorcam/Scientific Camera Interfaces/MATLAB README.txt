MATLAB README

For MATLAB support for all Thorlabs DCC- and DCU-series cameras, please see the DCx Camera Support folder typically installed at C:\Program Files\Thorlabs\Scientific Imaging\DCx Camera Support. MATLAB support is provided through the .NET interface.

For MATLAB support for all Thorlabs Scientific Cameras (340xxx, 1500xxx, 1501xxx, 4070xxx, 8050xxx, 8051xxx, CS2100M-USB, CC215MU, CS135xxx, CS165xxx, CS235xxx, CS505xxx, CS895xxx), please use the .NET camera interface by following these directions:

1. Install ThorCam and the appropriate drivers using the installer CD that came with a camera or download an installer from the appropriate product page at Thorlabs.com.

2. Copy the managed DLLs from

 Scientific Camera Interfaces\SDK\DotNet Toolkit\dlls\Managed_64_lib\*.dll 
 
 to the same folder with your MATLAB .m files.

3. See the following guides found in the Documentation folder (usually C:\Program Files\Thorlabs\Scientific Imaging\Documentation\Scientific Camera Documents):
 
 TSI_Camera_MATLAB_Interface_Guide.pdf
 TSI_Camera_DotNET-LabVIEW-MATLAB_Programming_Guide.chm
 