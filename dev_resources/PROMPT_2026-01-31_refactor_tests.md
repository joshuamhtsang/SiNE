# Refactor of tests in SiNE repository

## Objective

In order to support the increasing complexity of adding new features into SiNE, to have an organised and thought-out set of unit and integration tests to form guardrails for the claude/AI-assisted code development.

## Current status

Tests (both unit and integration) are in the the [tests/](../tests/) directory.

Integration tests are in:
[integration](../tes.ts/integration/)

Unit tests are spread across the other directories in:
[tests/](../tests/).

Tests encompass things such as:

1. Integration tests:
    - Spinning up channel server and 'sine deploy' topologies
    - Connectivity tests
    - TCP throughput tests
    - The setting of netem parameters is correct
    - Uses the fixtures in [](../tests/integration/fixtures.py)


2. Unit tests:
    - Test expected output of specific functions in SiNE


## Goals/Aspirations

### Tests directory structure

To have the tests divided into well thought-out directory structure. Good categories to divide out the tests revolve around the main 'modes' of SiNE operation:

1. Shared bridge vs. Point-to-point: 

    Shared bridge network emulations rely on a namespace bridge, along with tc flower filters to define per-destination netem parameters. Example: [here](../examples/manet_triangle_shared/) and [here](../examples/manet_triangle_shared_sinr/). They are used for MANET-type networks. Point-to-point is more straight-forward with one set of netem parameters per egress link.

2. Sionna engine vs Fallback engine:

    The Sionna engine and fallback engine can fundamentally yield quite different results, since Sionna does ray tracing in an actual scene and the fallback engine is mostly(?) just FSPL calculation.

3. SNR vs SINR:

    The integration tests for when SINR-mode is enabled can yield different results to when only SNR is enabled.

A first-guess at what the tests/ directory *might* look like:

~~~
tests/point-to-point/sionna-engine/snr/
tests/point-to-point/sionna-engine/sinr/
tests/point-to-point/fallback-engine/snr/
tests/point-to-point/fallback-engine/sinr/

tests/shared-bridge/sionna-engine/snr/
tests/shared-bridge/sionna-engine/sinr/
tests/shared-bridge/fallback-engine/snr/
tests/shared-bridge/fallback-engine/sinr/
~~~

I expect the actual pytest functions to be separated into the corresponding directories.  Do suggest if you have a better idea of how to structure this directory.

### Pytests

Keep in mind that some of the tests in tests/ create their own 'network.yaml' inside the python script.  I prefer any test to always use a network.yaml in the examples/for_tests/.

### Examples directory structure

The [here](../examples/) directory should be divided into tests-specific and for-user directories. Perhaps:

~~~
examples/for_tests/  # These are examples the pytests in tests will reference, as they already do in say [here](../tests/integration/test_manet_shared_bridge.py).

examples/for_user/  # These are for the end-user to use and are the examples that [here](../README.md) should point the user towards for examples to demonstrate SiNE functionality.
~~~

This *might* mean some replication between these two directories, but that's okay. This directory structure allows more test-specific, contrived examples to exist in examples/for_tests/.

### Ensure fixtures are used where possible

Ensure fixtures like [here](./tests/integration/fixtures.py) are used whenever possible.

### Claude Code Stuff

Claude Code should understand this testing directory structure. Add basic pointers in CLAUDE.md and [here](../.claude/CLAUDE.md) to ensure:

1. README.md references examples in [here](examples/for_user/)

2. Integration tests use network.yaml test examples in [here](examples/for_tests/) whenever possible.