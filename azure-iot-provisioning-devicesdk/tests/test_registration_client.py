# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import pytest
from azure.iot.provisioning.devicesdk.registration_client import RegistrationClient


def test_raises_exception_on_init_of_abstract_transport(mocker):
    fake_transport = mocker.MagicMock
    with pytest.raises(TypeError):
        RegistrationClient(fake_transport)
