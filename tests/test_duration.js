import {parseDuration} from '../extension/duration.js';

const cases = [
    ['1', 1],
    ['300', 300],
    [' 42 ', 42],
    ['0', null],
    ['301', null],
    ['1.5', null],
    ['ten', null],
    ['', null],
];

for (const [input, expected] of cases) {
    const actual = parseDuration(input);
    if (actual !== expected)
        throw new Error(`${JSON.stringify(input)} returned ${actual}, expected ${expected}`);
}
