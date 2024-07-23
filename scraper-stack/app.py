#!/usr/bin/env python3

import aws_cdk as cdk
from cdk_stack import HeatRiskAnalysisStack

app = cdk.App()
HeatRiskAnalysisStack(app, "HeatRiskAnalysisStack")
app.synth()