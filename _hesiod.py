# A pure Python implementation of https://github.com/ebroder/python-hesiod/blob/master/_hesiod.pyx
# Requires PyDNS (http://pydns.sourceforge.net/)

import DNS
import os
import re


class HesiodContext(object):
    lhs = ".ns"
    rhs = ".athena.mit.edu"
    classes = [DNS.Class.IN, DNS.Class.HS]
    def __str__(self):
        return "HesiodContext(%s%s, %s)" % (self.lhs, self.rhs, self.classes)


def read_config_file(context, filename):
    with open(filename, 'r') as f:
        for line in f.readlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            matches = re.compile('^([A-z]+)\s*=\s*([A-z.,]+)$').match(line)
            if matches:
                key = matches.group(1)
                value = matches.group(2)
                if key == 'lhs':
                    context.lhs = value
                elif key == 'rhs':
                    context.rhs = value
                elif key == 'classes':
                    classes = value.split(',')
                    for i in range(len(classes)):
                        if i == len(context.classes):
                            break
                        context.classes[i] = {'IN': DNS.Class.IN,
                                               'HS': DNS.Class.HS}.get(classes[i],
                                                                       DNS.Class.IN)


def hesiod_init(context):
    configname = os.environ.get("HESIOD_CONFIG", "/etc/hesiod.conf")
    read_config_file(context, configname)
    context.rhs = os.environ.get("HES_DOMAIN", context.rhs)
    if not context.lhs.startswith('.'):
        context.lhs = '.' + context.lhs
    if not context.rhs.startswith('.'):
        context.rhs = '.' + context.rhs


def hesiod_end(context):
    del context


def hesiod_to_bind(context, name, type):
    if '@' in name:
        for i in range(len(name)):
            if name[i] == '@':
                break
        name[i] = 0
        rest = name[i+1:]
        if '.' in rest:
            rhs = rest
        else:
            rhs = hesiod_resolve(context, rest, "rhs-extension")
    else:
        rhs = context.rhs
    name += '.' + type + context.lhs + rhs
    return name


def hesiod_resolve(context, name, type):
    return get_txt_records(context, hesiod_to_bind(context, name, type))

def get_txt_records(context, name):
    nameservers = []
    with open("/etc/resolv.conf", 'r') as f:
        for line in f.readlines():
            line.strip()
            if line.startswith('nameserver'):
                _, nameserver = line.split(' ')
                nameservers.append(nameserver)
    result = None
    for nameserver in nameservers:
        try:
            result = DNS.Request(name=name, qtype='TXT', server=nameserver).req()
            break
        except DNS.DNSError:
            pass
    if not result or len(result.answers) == 0:
        raise DNS.DNSError("Unable to resolve %r using nameservers %r" % (name, nameservers))
    return result.answers[0]['data']


