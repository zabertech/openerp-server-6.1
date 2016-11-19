from exceptions import NotImplementedError

class test(object):
    def __init__(self, args):
        self.args = args

    def validate(self, value):
        try:
            result = self.test(value)
            if not result:
                raise
            return (True,)
        except Exception as err:
            return (False, self.error_msg)

    def test(self, value):
        raise NotImplementedError()
    
class is_true(test):
    def __init__(self, args):
        super(is_true, self).__init__(args)
        self.error_msg = "Expected \"True\""

    def test(self, value):
        return bool(value)
        
class is_false(test):
    def __init__(self, args):
        super(is_false, self).__init__(args)
        self.error_msg = "Expected \"False\""
        
    def test(self, value):
        return not bool(value)

class is_like(test):
    def __init__(self, args):
        super(is_like, self).__init__(args)
        self.error_msg = "Expected to match pattern \"{}\"".format(args['pattern'])

    def test(self, value):
        import re
        return bool(re.match(self.args['pattern'], value))

class is_not_like(test):
    def __init__(self, args):
        super(is_not_like, self).__init__(args)
        self.error_msg = "Expected to not match pattern \"{}\"".format(args['pattern'])

    def test(self, value):
        import re
        return not bool(re.match(self.args['pattern'], value))

class is_numeric_string(test):
    def __init__(self, args):
        super(is_numeric_string, self).__init__(args)
        self.error_msg = "Expected a numeric string"

    def test(self, value):
        return value.isdigit()

class is_nonnumeric_string(test):
    def __init__(self, args):
        super(is_nonnumeric_string, self).__init__(args)
        self.error_msg = "Expected a non-numeric string"

    def test(self, value):
        return (isinstance(value, str) or isinstance(value, unicode)) and not value.isdigit()

class is_string(test):
    def __init__(self, args):
        super(is_string, self).__init__(args)
        self.error_msg = "Expected a string"

    def test(self, value):
        return isinstance(value, str) or isinstance(value, unicode)

class is_empty_string(test):
    def __init__(self, args):
        super(is_empty_string, self).__init__(args)
        self.error_msg = "Expected an empty string"

    def test(self, value):
        return (isinstance(value, str) or isinstance(value, unicode)) and not len(value)

class is_nonempty_string(test):
    def __init__(self, args):
        super(is_nonempty_string, self).__init__(args)
        self.error_msg = "Expected a non-empty string"

    def test(self, value):
        return len(value) and isinstance(value, str) or isinstance(value, unicode)

class is_equal_to(test):
    def __init__(self, args):
        super(is_equal_to, self).__init__(args)
        self.error_msg = "Expected \"{}\"".format(args['value'])

    def test(self, value):
        return value == self.args['value']

class is_nonequal_to(test):
    def __init__(self, args):
        super(is_nonequal_to, self).__init__(args)
        self.error_msg = "Expected a value other than \"{}\"".format(args['value'])

    def test(self, value):
        return value != self.args['value']

class is_in(test):
    def __init__(self, args):
        super(is_in, self).__init__(args)
        self.error_msg = "Expected one of \"{}\"".format(args['value'])
    
    def test(self, value):
        return value in self.args['value']

class has(test):
    def __init__(self, args):
        super(has, self).__init__(args)
        self.error_msg = "Expected \"{}\"".format(args['value'])
    
    def test(self, value):
        return self.args['value'] in value

class is_not_in(test):
    def __init__(self, args):
        super(is_not_in, self).__init__(args)
        self.error_msg = "Expected other than one of \"{}\"".format(args['value'])

    def test(self, value):
        return value not in self.args['value']

class has_not(test):
    def __init__(self, args):
        super(has_not, self).__init__(args)
        self.error_msg = "Expected other than \"{}\"".format(args['value'])
    
    def test(self, value):
        return self.args['value'] not in value

class profile(object):
    
    def __init__(self, tests):
        self.tests = tests

    def validate(self, data):
        results = {}
        for field, tests in self.tests.items():
            if not field in results:
                results[field] = []
            for test, args in tests:
                results[field].append(test(args).validate(data[field]))
        return results

    def score(self, results):
        score = 0
        for key, vals in results.items():
            if not False in [v[0] for v in vals]:
                score += 1
        if score > 0:
            score =  float(score) / len(self.tests)
        return score

    def errors(self, results):
        errors = {}
        for key, vals in results.items():
            for v in vals:
                if v[0]:
                    continue
                if not key in errors:
                    errors[key] = []
                errors[key].append(v[1])
        return errors

