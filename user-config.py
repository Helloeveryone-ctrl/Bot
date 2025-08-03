from collections import defaultdict

family = 'wikipedia'
mylang = 'test'

usernames = defaultdict(
    lambda: defaultdict(str),
    {
        'wikipedia': defaultdict(str, {
            'test': 'CactusismeBot',  # Your bot username here
        }),
    }
)

password_file = defaultdict(
    lambda: defaultdict(str),
    {
        'wikipedia': defaultdict(str, {
            'test': 'Temporarybotpassword',  # Your bot password here
        }),
    }
)
