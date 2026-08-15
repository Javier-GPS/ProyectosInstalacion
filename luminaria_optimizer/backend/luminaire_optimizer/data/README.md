# Photometric Data

This directory is reserved for versioned input data used by the optimizer.

- `group/` contains the measured or simulated LDT of the three-LED group.
- `rtables/` contains R1-R4 and the special low-height C2 table.

The original user-supplied files remain in `Downloads` until they are copied
here after confirming their provenance and version. Runtime code accepts an
explicit file or Base64 payload and never assumes a particular local path.
