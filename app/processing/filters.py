from scipy.signal import butter, filtfilt

def butter_bandpass(data, low, high, fs, order=4):
    # filtfilt requires data length > padlen (which is 3*max(len(a), len(b)))
    # For order=4, this needs ~27 samples. Reduce order for small data.
    min_length = 3 * (2 * order + 1)

    if data.shape[-1] < min_length:
        if data.shape[-1] >= 10:
            order = 1
        else:
            return data

    b, a = butter(order, [low/fs*2, high/fs*2], btype="band")
    return filtfilt(b, a, data)

def notch(data, freq, fs, quality=30):
    if data.shape[-1] < 15:
        return data

    b, a = butter(2, [freq/(fs/2)-freq/(fs/2)/quality, freq/(fs/2)+freq/(fs/2)/quality], btype="bandstop")
    return filtfilt(b, a, data)

def rectify(data):
    return abs(data)

