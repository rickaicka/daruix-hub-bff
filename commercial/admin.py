from django.contrib import admin

from commercial.models import (
    Address,
    BusinessSegment,
    CompanyType,
    Contact,
    Department,
    Division,
    Party,
    Project,
    Proposal,
    ProposalContact,
    ProposalInstallment,
    ProposalRequestedService,
    ProposalType,
)

admin.site.register((
    Party,
    Address,
    Contact,
    Proposal,
    BusinessSegment,
    CompanyType,
    Division,
    Department,
    Project,
    ProposalType,
    ProposalRequestedService,
    ProposalContact,
    ProposalInstallment,
))
