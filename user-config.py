from collections import defaultdict

family = 'wikipedia'
mylang = 'test'

usernames = defaultdict(
    lambda: defaultdict(str),
    {
        'wikipedia': defaultdict(str, {
            'test': 'CactusismeBot',  # your bot username here
        }),
    }
)

# DO NOT define password_file here — remove this variable completely.
