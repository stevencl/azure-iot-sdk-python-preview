# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
"""
This module contains constants related to the transport package.
"""

__all__ = [
    "USER_AGENT",
    "API_VERSION",
    "SUBSCRIBE_TOPIC_PROVISIONING",
    "PUBLISH_TOPIC_REGISTRATION",
]

USER_AGENT = "azure-iot-provisioning-devicesdk" + "/" + "0.0.1"
"""
Default interval for polling, to use in case service doesn't provide it to us.
"""
POLLING_INTERVAL = 2000

"""
api version to use while communicating with service.
"""
API_VERSION = "2018-11-01"
"""
Timeout to use when communicating with the service
"""
DEFAULT_TIMEOUT = 30000

SUBSCRIBE_TOPIC_PROVISIONING = "$dps/registrations/res/#"
"""
The first part of the topic string used for publishing.
The registration request id (rid) is appended to this.
"""
PUBLISH_TOPIC_REGISTRATION = "$dps/registrations/PUT/iotdps-register/?$rid="
