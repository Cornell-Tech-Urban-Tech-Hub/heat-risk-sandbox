#!/usr/bin/env python3

import aws_cdk as cdk
from scraper_stack.heat_risk_analysis_stack import HeatRiskAnalysisStack

app = cdk.App()
HeatRiskAnalysisStack(app, "HeatRiskAnalysisStack")
app.synth()