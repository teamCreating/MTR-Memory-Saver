# Revised 0.4.8 performance preparation only

Four fresh NF248 templates were prepared without launching a qualification or
scheduled trial: unchanged 0.3.0 baseline and revised 0.4.8 candidate, each in
plain/profile mode. Candidate SHA is `943b3d455fa3ce9d3ede74bc1a2071ece7bf70b09d9b7f829027347b53a9b588`;
baseline SHA is `b9c95bbe79c6c76fe6a0c9af6bdb4f9ed7ce6b007fecdb1c9f543544ce562f02`.
All use the same neutral observer 1.0.3, sixteen pack fingerprints, immutable
copied source world, 3 GiB maximum/512 MiB initial heap and 1280×720 resolution.
Profile adds full-history JFR; neither mode enables NMT. The existing experiment
policy remains unchanged. Its actual qualification and execution gates remain
required before constructing or claiming scheduled A/A and A/B replicates.

The previous scenario/camera/route declarations were retained; current CIM,
power-scheme and selected background-process observations replace their old
machine-context snapshot. No process, power mode or permission was changed.
Concurrent user applications are present. A timestamped snapshot does not
establish equal background load during future measurements.

Two initial preparation failures are retained: the selected installed baseline
JAR lacked its adjacent original manifest, then the selected installed observer
JAR lacked its manifest. Original sidecars were recovered from the old frozen
preparation controls and verified against the pinned baseline/observer bytes.
Neither failure launched a JVM or created a substitute measurement. The third
preparation attempt completed all four commands with actual exit zero.

These are post-run reference copies of scripts, receipts, plans and controls.
The copied JARs are this project's historical baseline and neutral observer;
the revised candidate has its separately named engineering-051 artifact seal.
No world, MTR, dependency, JFR or ETL payloads are copied. Individual template
plans still record their original absolute preparation paths.

**No performance acceptance:** four actual qualifications, independent frame
source/positive control, observer-off calibration, scheduled trials and final
paired analysis remain outstanding. The raw ETW diagnostic failures are in the
adjacent frame-source-diagnostics evidence. Preparation cannot quantify savings.
