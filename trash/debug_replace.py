src = open(r'e:\Users\abhihub\New folder\abhihub\methods\supabase_helper.py', encoding='utf-8').read()
lines = src.split('\r\n')
print(f'Total lines: {len(lines)}')
for i in range(67, 76):
    print(f'L{i+1}: {repr(lines[i])}')
print()
print('--- Testing replacement ---')
old = '        uuid.UUID(str(val))\r\n        return True\r\n    except:\r\n        return False'
print(f'old in src: {old in src}')
# try with \n
old2 = '        uuid.UUID(str(val))\n        return True\n    except:\n        return False'
print(f'old2 (LF) in src: {old2 in src}')
