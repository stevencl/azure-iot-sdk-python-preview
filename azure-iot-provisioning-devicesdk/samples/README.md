# Samples for the Azure IoT Provisioning Devices SDK

This directory contains simple samples showing how to use the various features of the Microsoft Azure IoT Hub Device Provisioning Service from devices running Python.


## List of Samples
* Register a device using an symmetric key authentication individual enrollment.


## How to run the samples
Our samples rely on having some environment variables :-
* `PROVISIONING_HOST` - Host running the Device Provisioning Service. Can be found in the Azure portal in the Overview tab as the string Global device endpoint
* `PROVISIONING_IDSCOPE` - Used to uniquely identify the specific provisioning service the device will register through. Can be found in the Azure portal in the Overview tab as ID scope.
* `PROVISIONING_REGISTRATION_ID` - Used to uniquely identify a device in the Device Provisioning Service. Can be found in the Azure portal in the Manage Enrollments section as registration id.
* `PROVISIONING_SYMMETRIC_KEY` - The key which will be used to create the shared access signature token to authenticate the device. Can be found in the Azure portal in the details of an enrollment as primary or secondary key.

