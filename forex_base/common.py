
# Format seconds into a string of the form 'HH:MM:SS'
def format_time(seconds):
    diff_sec = int(seconds)
    hours = abs(diff_sec) // 3600
    minutes = (abs(diff_sec) % 3600) // 60
    seconds = abs(diff_sec) % 60
    sign = '-' if diff_sec < 0 else ''
    return f"{sign}{hours:02}:{minutes:02}:{seconds:02}"