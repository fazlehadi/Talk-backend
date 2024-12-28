import secrets

def generate_unique_id(length=6):
  characters = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%&=/><-+'
  return ''.join(secrets.choice(characters) for _ in range(length))
