# Resume 1.1 shared public budget metric

This note freezes the acceptance metric used by the 0.5.2 source-candidate tests after independent review found successive metadata bypasses. It is a contract clarification, not a release claim.

The hard maximum is **16 KiB (16,384 bytes)** across governed public material in the `data` object of the `resume` envelope.

## Traversal

Walk the `data` JSON value recursively with a hard maximum of 10,000 visited value/key nodes.

Count:

- every object key: UTF-8 byte length of the key;
- every string value: UTF-8 byte length of the string value;
- `null`: 4 bytes (`null`);
- booleans: 4 bytes for `true`, 5 bytes for `false`;
- integers: byte length of their canonical decimal JSON representation, including a leading minus sign when present.

The current documented resume contract has no floating-point fields. A floating-point value in governed resume metadata is therefore invalid/fail-closed rather than an unbudgeted escape hatch.

JSON structural punctuation and the quote characters surrounding strings/keys are not counted by this contract metric. This is deliberately a stable logical budget rather than a promise to equal the serializer's complete wire length.

## `bytes` declaration

The public `bytes` key and its integer value are themselves governed public metadata. Therefore a valid packet uses the small fixed point induced by the decimal digit length of its own declaration:

1. calculate the metric including the current integer value of `bytes`;
2. set `bytes` to that metric;
3. repeat until unchanged (normally one additional iteration after the digit width changes).

Acceptance requires:

```text
bytes == measured_public_budget
0 <= bytes <= maxBytes <= 16384
```

This closes the reviewed bypasses involving giant object keys, giant nested integers/scalars, routing arrays and metadata outside `content`.

## Required vocabulary

For resume data schema `1.1`, `ledgerStatus` is restricted to:

```text
missing | ready | corrupt
```

Unknown arbitrary strings are not forward-compatible success values. A future vocabulary expansion requires a schema/contract update plus tests.

## Implementer note

`tools/verify_upgrade_052.py` and `rust/mission-center-cli/tests/upgrade_052_contract.rs` must implement the same metric. Do not weaken one side merely to make a candidate pass the other.
