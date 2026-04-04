(function initPEffortCommon(globalScope) {
    const DEFAULT_ZONES = [
        { min: 0, max: 60, color: '#009e80', name: 'Z1' },
        { min: 60, max: 80, color: '#009e00', name: 'Z2' },
        { min: 80, max: 90, color: '#ffcb0e', name: 'Z3' },
        { min: 90, max: 105, color: '#ff7f0e', name: 'Z4' },
        { min: 105, max: 135, color: '#dd0447', name: 'Z5' },
        { min: 135, max: 300, color: '#6633cc', name: 'Z6' },
        { min: 300, max: 999, color: '#504861', name: 'Z7' },
    ];

    function fmtDur(seconds) {
        const s = Math.round(seconds || 0);
        const m = Math.floor(s / 60);
        const r = s % 60;
        return m > 0 ? `${m}m${r}s` : `${s}s`;
    }

    function calculateTimeBasedMovingAverage(values, timeValues, windowSeconds) {
        const n = Math.min(values.length, timeValues.length);
        if (!n) return [];

        const result = new Array(n);
        let lo = 0;
        let hi = 0;
        let sum = 0;
        let count = 0;

        for (let i = 0; i < n; i++) {
            const center = timeValues[i];
            const winLo = center - windowSeconds / 2;
            const winHi = center + windowSeconds / 2;

            while (hi < n && timeValues[hi] <= winHi) {
                sum += values[hi];
                count++;
                hi++;
            }
            while (lo < hi && timeValues[lo] < winLo) {
                sum -= values[lo];
                count--;
                lo++;
            }
            result[i] = count > 0 ? sum / count : values[i];
        }

        return result;
    }

    function getIntensityZones(options) {
        const cfg = options || {};
        const storage = cfg.storage || globalScope.localStorage;
        const keys = Array.isArray(cfg.keys) ? cfg.keys : [];

        if (storage && keys.length > 0) {
            for (const key of keys) {
                const stored = storage.getItem(key);
                if (!stored) continue;
                try {
                    const parsed = JSON.parse(stored);
                    if (Array.isArray(parsed) && parsed.length > 0) {
                        return parsed;
                    }
                } catch (_) {
                    // Ignore malformed persisted zones and continue fallback chain.
                }
            }
        }

        if (Array.isArray(cfg.fallbackZones) && cfg.fallbackZones.length > 0) {
            return cfg.fallbackZones;
        }

        return DEFAULT_ZONES;
    }

    globalScope.PEffortCommon = {
        DEFAULT_ZONES,
        fmtDur,
        calculateTimeBasedMovingAverage,
        getIntensityZones,
    };
})(window);
