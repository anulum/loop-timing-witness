// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — consumer-owned reviewed neural registrations

//! Map an admission identity to the consumer's own reviewed source entry.
//!
//! Acquisition data selects neither the registry nor an entry. A consumer that
//! reviews its own source policy, checker policy and executor may build a
//! registry and pass it to [`crate::load_neural_run_with_registry`].

use crate::files::digest;
use crate::public_image::{ImageExecutor, NeuralExecutor};
use crate::public_runtime::Installation;
use std::collections::BTreeMap;

/// Admission identity: schema ID, schema digest, source cohort and source-contract digest.
pub type NeuralKey = (String, String, String, String);

/// Deferred construction of one reviewed entry; host files are read only when selected.
pub type NeuralFactory = Box<dyn Fn() -> Result<NeuralEntry, String>>;

/// Reviewed source policy, checker policy and checker executor of one registration.
pub struct NeuralEntry {
    pub(crate) policy: Vec<u8>,
    pub(crate) checker: Vec<u8>,
    pub(crate) executor: NeuralExecutor,
}

impl NeuralEntry {
    /// Combine reviewed policy bytes with a host installation.
    pub fn host(policy: Vec<u8>, checker: Vec<u8>, installation: Installation) -> Self {
        Self {
            policy,
            checker,
            executor: NeuralExecutor::Host(Box::new(installation)),
        }
    }

    /// Combine reviewed policy bytes with an immutable checker image executor.
    pub fn image(policy: Vec<u8>, checker: Vec<u8>, executor: ImageExecutor) -> Self {
        Self {
            policy,
            checker,
            executor: NeuralExecutor::Image(Box::new(executor)),
        }
    }
}

/// Consumer-owned map from admission identity to its reviewed entry factory.
#[derive(Default)]
pub struct NeuralRegistry {
    entries: BTreeMap<NeuralKey, NeuralFactory>,
}

impl NeuralRegistry {
    /// Return an empty registry that admits no acquisition.
    pub fn new() -> Self {
        Self::default()
    }

    /// Register one reviewed entry factory under its admission identity.
    pub fn insert(&mut self, key: NeuralKey, factory: NeuralFactory) {
        self.entries.insert(key, factory);
    }

    /// Return the packaged registry of the reviewed host and image entries.
    pub fn reviewed() -> Self {
        let mut registry = Self::new();
        for (policy, checker, executor) in [
            (
                &include_bytes!("../public-data/neural-selected-source-contract.json")[..],
                &include_bytes!("../public-data/neural-selected-checker-policy.json")[..],
                crate::selected_profile::installation as fn() -> Result<NeuralExecutor, String>,
            ),
            (
                &include_bytes!("../public-data/neural-image-source-contract.json")[..],
                &include_bytes!("../public-data/neural-image-checker-policy.json")[..],
                crate::selected_profile::image,
            ),
        ] {
            registry.insert(
                neural_key(digest(policy)),
                Box::new(move || {
                    Ok(NeuralEntry {
                        policy: policy.to_vec(),
                        checker: checker.to_vec(),
                        executor: executor()?,
                    })
                }),
            );
        }
        registry
    }

    /// Return the factory registered for one admission identity.
    pub(crate) fn get(&self, key: &NeuralKey) -> Option<&NeuralFactory> {
        self.entries.get(key)
    }
}

/// Build the admission identity of a source contract under the approved carrier.
pub fn neural_key(source_contract_sha256: String) -> NeuralKey {
    (
        crate::public_policy::ID.to_owned(),
        crate::public_manifest::SCHEMA_SHA256.to_owned(),
        crate::public_policy::COHORT.to_owned(),
        source_contract_sha256,
    )
}
