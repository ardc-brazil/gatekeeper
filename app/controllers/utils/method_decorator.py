def decorate_per_method(methods, validator):
    '''Decorator for validating request methods, specially useful if you need to apply'''
    methods = [name.lower() for name in methods]
    def inner(meth):
        if meth.__name__ not in methods:
             return meth
        return validator(meth)
    return inner