# Copyright 2014 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Requires Python 2.4+ and Openssl 1.0+
#

import os
import sys
import traceback
import atexit
import json
import time
import datetime
import threading
import platform

from datetime import datetime

import azurelinuxagent.common.logger as logger

from azurelinuxagent.common.exception import EventError, ProtocolError
from azurelinuxagent.common.future import ustr
from azurelinuxagent.common.protocol.restapi import TelemetryEventParam, \
    TelemetryEventList, \
    TelemetryEvent, \
    set_properties, get_properties
from azurelinuxagent.common.version import DISTRO_NAME, DISTRO_VERSION, \
    DISTRO_CODE_NAME, AGENT_VERSION, \
    CURRENT_AGENT, CURRENT_VERSION


class WALAEventOperation:
    ActivateResourceDisk = "ActivateResourceDisk"
    Disable = "Disable"
    Download = "Download"
    Enable = "Enable"
    HealthCheck = "HealthCheck"
    HeartBeat = "HeartBeat"
    Install = "Install"
    InitializeHostPlugin = "InitializeHostPlugin"
    ProcessGoalState = "ProcessGoalState"
    Provision = "Provision"
    ReportStatus = "ReportStatus"
    Restart = "Restart"
    UnhandledError = "UnhandledError"
    UnInstall = "UnInstall"
    Upgrade = "Upgrade"
    Update = "Update"


class EventLogger(object):
    def __init__(self):
        self.event_dir = None

    def save_event(self, data):
        if self.event_dir is None:
            logger.warn("Event reporter is not initialized.")
            return

        if not os.path.exists(self.event_dir):
            os.mkdir(self.event_dir)
            os.chmod(self.event_dir, 0o700)

        existing_events = os.listdir(self.event_dir)
        if len(existing_events) >= 1000:
            existing_events.sort()
            oldest_files = existing_events[:-999]
            logger.warn("Too many files under: {0}, removing oldest".format(self.event_dir))
            try:
                for f in oldest_files:
                    os.remove(os.path.join(self.event_dir, f))
            except IOError as e:
                raise EventError(e)

        filename = os.path.join(self.event_dir,
                                ustr(int(time.time() * 1000000)))
        try:
            with open(filename + ".tmp", 'wb+') as hfile:
                hfile.write(data.encode("utf-8"))
            os.rename(filename + ".tmp", filename + ".tld")
        except IOError as e:
            raise EventError("Failed to write events to file:{0}", e)

    def add_event(self, name, op="", is_success=True, duration=0,
                  version=CURRENT_VERSION,
                  message="", evt_type="", is_internal=False):
        event = TelemetryEvent(1, "69B669B9-4AF8-4C50-BDC4-6006FA76E975")
        event.parameters.append(TelemetryEventParam('Name', name))
        event.parameters.append(TelemetryEventParam('Version', str(version)))
        event.parameters.append(TelemetryEventParam('IsInternal', is_internal))
        event.parameters.append(TelemetryEventParam('Operation', op))
        event.parameters.append(TelemetryEventParam('OperationSuccess',
                                                    is_success))
        event.parameters.append(TelemetryEventParam('Message', message))
        event.parameters.append(TelemetryEventParam('Duration', duration))
        event.parameters.append(TelemetryEventParam('ExtensionType', evt_type))

        data = get_properties(event)
        try:
            self.save_event(json.dumps(data))
        except EventError as e:
            logger.error("{0}", e)


__event_logger__ = EventLogger()


def elapsed_milliseconds(utc_start):
    d = datetime.utcnow() - utc_start
    return int(((d.days * 24 * 60 * 60 + d.seconds) * 1000) + \
                    (d.microseconds / 1000.0))

def report_event(op, is_success=True, message=''):
    from azurelinuxagent.common.version import AGENT_NAME, CURRENT_VERSION
    add_event(AGENT_NAME,
              version=CURRENT_VERSION,
              is_success=is_success,
              message=message,
              op=op)


def add_event(name, op="", is_success=True, duration=0, version=CURRENT_VERSION,
              message="", evt_type="", is_internal=False, log_event=True,
              reporter=__event_logger__):
    if log_event or not is_success:
        log = logger.info if is_success else logger.error
        log("Event: name={0}, op={1}, message={2}", name, op, message)

    if reporter.event_dir is None:
        logger.warn("Event reporter is not initialized.")
        return
    reporter.add_event(name, op=op, is_success=is_success, duration=duration,
                       version=str(version), message=message, evt_type=evt_type,
                       is_internal=is_internal)


def init_event_logger(event_dir, reporter=__event_logger__):
    reporter.event_dir = event_dir


def dump_unhandled_err(name):
    if hasattr(sys, 'last_type') and hasattr(sys, 'last_value') and \
            hasattr(sys, 'last_traceback'):
        last_type = getattr(sys, 'last_type')
        last_value = getattr(sys, 'last_value')
        last_traceback = getattr(sys, 'last_traceback')
        error = traceback.format_exception(last_type, last_value,
                                           last_traceback)
        message = "".join(error)
        add_event(name, is_success=False, message=message,
                  op=WALAEventOperation.UnhandledError)


def enable_unhandled_err_dump(name):
    atexit.register(dump_unhandled_err, name)
