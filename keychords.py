
skey_map = set(['<tab>'])
modifiers = ['C', 'M']
modifier_set = set(modifiers)


def parse_keychords(s):
    return ['-'.join(normalize_modifiers(chord[:-1]) + parse_key(chord[-1]))
            for chord in [chord.split('-')
                          for chord in filter(lambda seq: len(seq) != 0, s.split(' '))]]


def parse_key(k):
    if len(k) > 1 and k not in skey_map:
        raise KeyError('Unknown special key: %s' % k)

    return k


def normalize_modifiers(ms):
    unknown_modifiers = filter(lambda m: m not in modifiers, ms)
    if unknown_modifiers:
        raise KeyError('Encountered unknown modifiers: %s' % unknown_modifiers)

    return sorted(ms, key=modifiers.index)
