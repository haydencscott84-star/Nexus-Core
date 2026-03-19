def test(hour):
    SLEEP_START_HOUR = 0
    SLEEP_END_HOUR = 5
    if SLEEP_START_HOUR > SLEEP_END_HOUR:
        if hour >= SLEEP_START_HOUR or hour < SLEEP_END_HOUR: return True
    else:
        if hour >= SLEEP_START_HOUR and hour < SLEEP_END_HOUR: return True
    return False

print(f"23:00 Sleep? {test(23)}") # Should be False
print(f"01:00 Sleep? {test(1)}")  # Should be True
print(f"04:00 Sleep? {test(4)}")  # Should be True
print(f"06:00 Sleep? {test(6)}")  # Should be False
