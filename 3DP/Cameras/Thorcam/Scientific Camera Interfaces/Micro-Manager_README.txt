Micro-Manager README

For Micro-Manager support for Thorlabs scientific and compact cameras, please follow these directions:

1. Install ThorCam and the appropriate drivers using the installer CD that came with a camera or download an installer from the appropriate product page at Thorlabs.com.

2. On 64-bit Windows, install 64-bit Micro-Manager. On 32-bit Windows, install 32-bit Micro-Manager. (Thorlabs cameras do not currently support 32-bit Micro-Manager on 64-bit Windows.)

3. From the Thorcam installation folder (usually C:\Program Files\Thorlabs\Scientific Imaging\Scientific Camera Support\), copy the file called Scientific_Camera_Interfaces.zip to a separate folder where you have sufficient permissions to unzip it (your documents folder, for example).

4. Unzip the Scientific_Camera_Interfaces.zip archive and it will create a folder hierarchy with a folder named Scientific Camera Interfaces at the top level.

5. Option 1:
   For Thorlabs 340xxx, 1500xxx, 1501xxx, 4070xxx, 8050xxx, 8051xxx cameras, navigate to \Scientific Camera Interfaces\SDK\Legacy\Native Scientific CCD Camera Toolkit\dlls

   Option 2:
   For Thorlabs CS2100M-USB, CC215MU, CS135xxx, CS165xxx, CS235xxx, CS505xxx, CS895xxx cameras, navigate to \Scientific Camera Interfaces\SDK\Native Compact Scientific Camera Toolkit\dlls

6. You will see a Native_32_lib and a Native_64_lib folder.

7. Choose the appropriate folder (Native_32_lib vs. Native_64_lib) based on whether you installed 64-bit Micro-Manager or 32-bit Micro-Manager.

8. Copy all the DLLs from that folder into the Micro-Manager installation folder.

9. In Micro-Manager, go to Tools->Hardware Configuration Wizard. Create or modify a configuration and click Next. Scroll through the available devices to find TSI->TSICam.