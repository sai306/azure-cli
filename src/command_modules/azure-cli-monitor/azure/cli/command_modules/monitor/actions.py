# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import argparse

from azure.cli.command_modules.monitor.util import (
    get_aggregation_map, get_operator_map, get_autoscale_operator_map,
    get_autoscale_aggregation_map, get_autoscale_scale_direction_map)


def timezone_name_type(value):
    from azure.cli.command_modules.monitor._autoscale_util import AUTOSCALE_TIMEZONES
    zone = next((x['name'] for x in AUTOSCALE_TIMEZONES if x['name'].lower() == value.lower()), None)
    if not zone:
        from knack.util import CLIError
        raise CLIError(
            "Invalid time zone: '{}'. Run 'az monitor autoscale profile list-timezones' for values.".format(value))
    return zone


def timezone_offset_type(value):

    try:
        hour, minute = str(value).split(':')
    except ValueError:
        hour = str(value)
        minute = None

    hour = int(hour)

    if hour > 14 or hour < -12:
        from knack.util import CLIError
        raise CLIError('Offset out of range: -12 to +14')

    if hour >= 0 and hour < 10:
        value = '+0{}'.format(hour)
    elif hour >= 10:
        value = '+{}'.format(hour)
    elif hour < 0 and hour > -10:
        value = '-0{}'.format(-1 * hour)
    else:
        value = str(hour)
    if minute:
        value = '{}:{}'.format(value, minute)
    return value


def period_type(value):

    import re

    def _get_substring(indices):
        if indices == tuple([-1, -1]):
            return ''
        return value[indices[0]: indices[1]]

    regex = r'(p)?(\d+y)?(\d+m)?(\d+d)?(t)?(\d+h)?(\d+m)?(\d+s)?'
    match = re.match(regex, value.lower())
    match_len = match.regs[0]
    if match_len != tuple([0, len(value)]):
        raise ValueError
    # simply return value if a valid ISO8601 string is supplied
    if match.regs[1] != tuple([-1, -1]) and match.regs[5] != tuple([-1, -1]):
        return value

    # if shorthand is used, only support days, minutes, hours, seconds
    # ensure M is interpretted as minutes
    days = _get_substring(match.regs[4])
    minutes = _get_substring(match.regs[6]) or _get_substring(match.regs[3])
    hours = _get_substring(match.regs[7])
    seconds = _get_substring(match.regs[8])
    return 'P{}T{}{}{}'.format(days, minutes, hours, seconds).upper()


# pylint: disable=too-few-public-methods
class ConditionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        from azure.mgmt.monitor.models import ThresholdRuleCondition, RuleMetricDataSource
        # get default description if not specified
        if namespace.description is None:
            namespace.description = ' '.join(values)
        if len(values) == 1:
            # workaround because CMD.exe eats > character... Allows condition to be
            # specified as a quoted expression
            values = values[0].split(' ')
        if len(values) < 5:
            from knack.util import CLIError
            raise CLIError('usage error: --condition METRIC {>,>=,<,<=} THRESHOLD {avg,min,max,total,last} DURATION')
        metric_name = ' '.join(values[:-4])
        operator = get_operator_map()[values[-4]]
        threshold = int(values[-3])
        aggregation = get_aggregation_map()[values[-2].lower()]
        window = period_type(values[-1])
        metric = RuleMetricDataSource(None, metric_name)  # target URI will be filled in later
        condition = ThresholdRuleCondition(operator, threshold, metric, window, aggregation)
        namespace.condition = condition


# pylint: disable=protected-access
class AlertAddAction(argparse._AppendAction):
    def __call__(self, parser, namespace, values, option_string=None):
        action = self.get_action(values, option_string)
        super(AlertAddAction, self).__call__(parser, namespace, action, option_string)

    def get_action(self, values, option_string):  # pylint: disable=no-self-use
        from knack.util import CLIError
        _type = values[0].lower()
        if _type == 'email':
            from azure.mgmt.monitor.models import RuleEmailAction
            return RuleEmailAction(custom_emails=values[1:])
        elif _type == 'webhook':
            from azure.mgmt.monitor.models import RuleWebhookAction
            uri = values[1]
            try:
                properties = dict(x.split('=', 1) for x in values[2:])
            except ValueError:
                raise CLIError('usage error: {} webhook URI [KEY=VALUE ...]'.format(option_string))
            return RuleWebhookAction(uri, properties)

        raise CLIError('usage error: {} TYPE KEY [ARGS]'.format(option_string))


class AlertRemoveAction(argparse._AppendAction):
    def __call__(self, parser, namespace, values, option_string=None):
        action = self.get_action(values, option_string)
        super(AlertRemoveAction, self).__call__(parser, namespace, action, option_string)

    def get_action(self, values, option_string):  # pylint: disable=no-self-use
        # TYPE is artificially enforced to create consistency with the --add-action argument
        # but it could be enhanced to do additional validation in the future.
        from knack.util import CLIError
        _type = values[0].lower()
        if _type not in ['email', 'webhook']:
            raise CLIError('usage error: {} TYPE KEY [KEY ...]'.format(option_string))
        return values[1:]


# pylint: disable=protected-access
class AutoscaleAddAction(argparse._AppendAction):
    def __call__(self, parser, namespace, values, option_string=None):
        action = self.get_action(values, option_string)
        super(AutoscaleAddAction, self).__call__(parser, namespace, action, option_string)

    def get_action(self, values, option_string):  # pylint: disable=no-self-use
        from knack.util import CLIError
        _type = values[0].lower()
        if _type == 'email':
            from azure.mgmt.monitor.models import EmailNotification
            return EmailNotification(custom_emails=values[1:])
        elif _type == 'webhook':
            from azure.mgmt.monitor.models import WebhookNotification
            uri = values[1]
            try:
                properties = dict(x.split('=', 1) for x in values[2:])
            except ValueError:
                raise CLIError('usage error: {} webhook URI [KEY=VALUE ...]'.format(option_string))
            return WebhookNotification(uri, properties)

        raise CLIError('usage error: {} TYPE KEY [ARGS]'.format(option_string))


class AutoscaleRemoveAction(argparse._AppendAction):
    def __call__(self, parser, namespace, values, option_string=None):
        action = self.get_action(values, option_string)
        super(AutoscaleRemoveAction, self).__call__(parser, namespace, action, option_string)

    def get_action(self, values, option_string):  # pylint: disable=no-self-use
        # TYPE is artificially enforced to create consistency with the --add-action argument
        # but it could be enhanced to do additional validation in the future.
        from knack.util import CLIError
        _type = values[0].lower()
        if _type not in ['email', 'webhook']:
            raise CLIError('usage error: {} TYPE KEY [KEY ...]'.format(option_string))
        return values[1:]


class AutoscaleConditionAction(argparse.Action):  # pylint: disable=protected-access
    def __call__(self, parser, namespace, values, option_string=None):
        from azure.mgmt.monitor.models import MetricTrigger
        if len(values) == 1:
            # workaround because CMD.exe eats > character... Allows condition to be
            # specified as a quoted expression
            values = values[0].split(' ')
        name_offset = 0
        try:
            metric_name = ' '.join(values[name_offset:-4])
            operator = get_autoscale_operator_map()[values[-4]]
            threshold = int(values[-3])
            aggregation = get_autoscale_aggregation_map()[values[-2].lower()]
            window = period_type(values[-1])
        except (IndexError, KeyError):
            from knack.util import CLIError
            raise CLIError('usage error: --condition METRIC {==,!=,>,>=,<,<=} '
                           'THRESHOLD {avg,min,max,total,count} PERIOD')
        condition = MetricTrigger(
            metric_name=metric_name,
            metric_resource_uri=None,  # will be filled in later
            time_grain=None,  # will be filled in later
            statistic=None,  # will be filled in later
            time_window=window,
            time_aggregation=aggregation,
            operator=operator,
            threshold=threshold
        )
        namespace.condition = condition


class AutoscaleScaleAction(argparse.Action):  # pylint: disable=protected-access
    def __call__(self, parser, namespace, values, option_string=None):
        from azure.mgmt.monitor.models import ScaleAction, ScaleType
        if len(values) == 1:
            # workaround because CMD.exe eats > character... Allows condition to be
            # specified as a quoted expression
            values = values[0].split(' ')
        if len(values) != 2:
            from knack.util import CLIError
            raise CLIError('usage error: --scale {in,out,to} VALUE[%]')
        dir_val = values[0]
        amt_val = values[1]
        scale_type = None
        if dir_val == 'to':
            scale_type = ScaleType.exact_count.value
        elif str(amt_val).endswith('%'):
            scale_type = ScaleType.percent_change_count.value
            amt_val = amt_val[:-1]  # strip off the percent
        else:
            scale_type = ScaleType.change_count.value

        scale = ScaleAction(
            direction=get_autoscale_scale_direction_map()[dir_val],
            type=scale_type,
            cooldown=None,  # this will be filled in later
            value=amt_val
        )
        namespace.scale = scale


class MultiObjectsDeserializeAction(argparse._AppendAction):  # pylint: disable=protected-access
    def __call__(self, parser, namespace, values, option_string=None):
        type_name = values[0]
        type_properties = values[1:]

        try:
            super(MultiObjectsDeserializeAction, self).__call__(parser,
                                                                namespace,
                                                                self.get_deserializer(type_name)(*type_properties),
                                                                option_string)
        except KeyError:
            raise ValueError('usage error: the type "{}" is not recognizable.'.format(type_name))
        except TypeError:
            raise ValueError(
                'usage error: Failed to parse "{}" as object of type "{}".'.format(' '.join(values), type_name))
        except ValueError as ex:
            raise ValueError(
                'usage error: Failed to parse "{}" as object of type "{}". {}'.format(
                    ' '.join(values), type_name, str(ex)))

    def get_deserializer(self, type_name):
        raise NotImplementedError()


class ActionGroupReceiverParameterAction(MultiObjectsDeserializeAction):
    def get_deserializer(self, type_name):
        from azure.mgmt.monitor.models import EmailReceiver, SmsReceiver, WebhookReceiver
        return {'email': EmailReceiver, 'sms': SmsReceiver, 'webhook': WebhookReceiver}[type_name]
