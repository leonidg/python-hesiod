# A pure Python implementation of https://github.com/ebroder/python-hesiod/blob/master/_hesiod.pyx
# Code strongly based on https://github.com/ebroder/libhesiod/blob/master/hesiod.c

# Requires PyDNS (http://pydns.sourceforge.net/) PyDNS is actually
# pretty crappy and among other things doesn't actually support using
# a DNS class other than C_IN.  C_IN worked for my purposes
# (specifically to get the /mit-automounter to work) so I'm going to
# go with it. This does mean that everything in this code implying
# that you can use another kind of DNS class is a lie.
import DNS

import os
import re
import threading

class HesiodContext(object):
    lhs = ".ns"
    rhs = ".athena.mit.edu"
    classes = [DNS.Class.IN, DNS.Class.HS]
    def __str__(self):
        return "HesiodContext(%s%s, %s)" % (self.lhs, self.rhs, self.classes)

__lookup_lock = threading.Lock()


def read_config_file(context, filename):
    """
    Parse configuration file (e.g. /etc/hesiod.conf) and fill out the
    context based on the results.
    """
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
    """
    Initialize the context with informatinon from the configuration
    file and environment variables.
    """
    configname = os.environ.get("HESIOD_CONFIG", "/etc/hesiod.conf")
    read_config_file(context, configname)
    context.rhs = os.environ.get("HES_DOMAIN", context.rhs)
    if not context.lhs.startswith('.'):
        context.lhs = '.' + context.lhs
    if not context.rhs.startswith('.'):
        context.rhs = '.' + context.rhs


def hesiod_end(context):
    """
    Free memory from the context. This exists for compatibility, as
    the Python GC should deal with it for us.
    """
    del context


def hesiod_to_bind(context, name, type):
    """
    Return the DNS name that will be used for the lookup
    """
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


def hesiod_resolve(context, name, type, nameservers=[]):
    """
    Perform the lookup of the given name and type
    """
    return get_txt_records(context, hesiod_to_bind(context, name, type), nameservers)


def get_txt_records(context, name, nameservers=[]):
    """
    Actually performs the lookup. This is a lower level function as it
    expects the correct bound DNS name, rather than the user-friendly
    Hesiod "name" and "type" values.

    The DNS module doesn't deal with figuring out nameservers for some
    reason, so if the nameserver is not provided as an argument, as a
    simple hack this function just parses /etc/resolv.conf itself and
    tries to use one nameserver at a time.
    """
    with open("/etc/resolv.conf", 'r') as f:
        for line in f.readlines():
            line = line.strip()
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


def bind(hes_name, hes_type):
    """
    Convert the provided arguments into a DNS name.
    
    The DNS name derived from the name and type provided is used to
    actually execute the Hesiod lookup.
    """
    return hesiod_to_bind(HesiodContext(), hes_name, hes_type)


def resolve(hes_name, hes_type, nameservers=[]):
    """
    Return a list of records matching the given name and type.
    """
    try:
        __lookup_lock.acquire()
        result = hesiod_resolve(HesiodContext(), hes_name, hes_type, nameservers)
    finally:
        __lookup_lock.release()
    return result
