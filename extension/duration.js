export const MIN_CUSTOM_DURATION = 1;
export const MAX_CUSTOM_DURATION = 300;

export function parseDuration(value) {
    const text = String(value).trim();
    if (!/^\d+$/.test(text))
        return null;
    const duration = Number.parseInt(text, 10);
    if (duration < MIN_CUSTOM_DURATION || duration > MAX_CUSTOM_DURATION)
        return null;
    return duration;
}
