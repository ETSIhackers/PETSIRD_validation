"""
Validation functions for PETSIRD files and objects.

All `validate` functions raise ValueError if there is a problem. Each module
registers its checks in a `<module>_tests_suite` dict, which cli.py runs.

There is one module per file in PETSIRD's model/ folder. Implemented so far:

- basic_types: model/BasicTypes.yml (helpers)
- detector_information: model/DetectorInformation.yml
- geometry_information: model/GeometryInformation.yml
- material_information: model/MaterialInformation.yml
- scanner_information: model/ScannerInformation.yml
- detection_efficiencies: model/DetectionEfficiencies.yml
- singles_histograms: model/SinglesHistograms.yml
- exam_information: model/ExamInformation.yml
- dicom_types: model/DICOMTypes.yml
- time_frame_information: model/TimeFrameInformation.yml
- events: model/Events.yml
- protocol: model/Protocol.yml
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo
