This directory contains an explicitly synthetic, expired gate-schema fixture
for exercising the canonical loader during zero-call executor qualification.
It is not an Owner decision, O2 receipt, real RC tag, operation package or
execution window. Its RC999999 and all-f commit identifiers are deliberately
fictional. The fixture expires in August 2026 and must remain inactive.

The schema's approval fields are synthetic test values labelled NOT_OWNER;
they do not grant runtime authority. No RC tag is created, no operation is
registered, and no credential value is present. Qualification checks a pinned
SHA, loads only this fixture into temporary private file staging, verifies it
is expired, and removes staging before reporting success. It never calls a
provider, reads provider plaintext or reserves budget.
