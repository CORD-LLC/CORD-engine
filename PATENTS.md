# Patents

This repository contains the reference implementation of the CORD specification. The implementation is open source under Apache 2.0 — read it, run it, fork it, build with it. This document explains the patent landscape so you can plan your own product accordingly.

## The patent

US patent application No. 64/034,169, filed April 2026, "Canonical Object for Relational Data" (CORD). The application claims include:

- The Envelope Fidelity Score (EFS) computation method
- PARTIAL coefficient bounds and confidence-based propagation
- The three-category conformance validation framework
- The four-tier conformance classification system
- The `application/cord+json` envelope format
- EFS as a cross-system fidelity metric

The non-provisional conversion deadline is April 9, 2027.

## What you can do without talking to us

Almost everything most people want to do.

- **Evaluate, prototype, build.** The Apache 2.0 license covers it.
- **Use the engine in your internal systems.** Apache 2.0 covers it.
- **Implement CORD from the spec, in any language, in any product.** The spec is Apache 2.0 and explicitly invites independent implementations.
- **Modify and redistribute the engine source.** Apache 2.0 covers it.
- **Use CORD-formatted envelopes in your data pipeline.** Apache 2.0 covers it.

If you're building a normal application that produces or consumes CORD envelopes, you don't need a patent license. The Apache 2.0 grant is sufficient.

## What needs a conversation

Three situations.

**Productizing fidelity scoring at scale.** If you're building a commercial product whose central value proposition is "we measure data fidelity" — particularly if you're marketing EFS or an EFS-equivalent metric as the deliverable — talk to us. The patent claims cover EFS as a cross-system industry metric.

**Certification authority.** "CORD-Compliant" is a designation tied to the CORD certification process. If you want to certify products as CORD-Compliant, you need to be authorized. See [cordspec.org/certification](https://cordspec.org/certification).

**Reselling or rebranding the reference engine.** Distributing modified versions for end-user use under Apache 2.0 is fine. Rebadging the reference engine and selling it as your own commercial product whose value depends on the patented methods is the situation where a license becomes relevant.

## What we want from this

The CORD specification stays open. Anyone can implement it. The reference engine stays open under Apache 2.0. The patent exists to fund three things:

1. Maintenance of the specification
2. Maintenance of the reference engine
3. The certification authority that gives "CORD-Compliant" credible meaning

The patent isn't there to gate adoption. It's there to make sure the standard has a steward.

## Contact

For licensing, certification, or any patent question: licensing@cordspec.org.
