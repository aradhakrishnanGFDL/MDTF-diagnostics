# Base OS
FROM ubuntu:latest
FROM mambaorg/micromamba:latest
# Container Metadata
LABEL maintainer="20195932+wrongkindofdoctor@users.noreply.github.com"
LABEL version="alpha-01"
LABEL description="This is a docker image for the MDTF-diagnostics package"
# Disable Prompt During Packages Installation
ARG DEBIAN_FRONTEND=noninteractive
RUN micromamba info
RUN micromamba shell hook --shell bash
# Copy the MDTF-diagnostics package contents from local machine to image
ENV CODE_ROOT=/proj/MDTF-diagnostics
COPY src ${CODE_ROOT}/src
COPY data ${CODE_ROOT}/data
#COPY diagnostics ${CODE_ROOT}/diagnostics
COPY mdtf_framework.py ${CODE_ROOT}
COPY shared ${CODE_ROOT}/shared
COPY sites ${CODE_ROOT}/sites
COPY tests ${CODE_ROOT}/tests
# Install conda environments
ENV CONDA_ROOT=/opt/conda/
ENV CONDA_ENV_DIR=/opt/conda/envs
RUN micromamba create -f /proj/MDTF-diagnostics/src/conda/env_base.yml
#cRUN micromamba activate _MDTF_base
# Verify installation
#RUN /proj/MDTF-diagnostics/mdtf_framework.py --help
# Run mdtf on src/default_tests.jsonc
# CMD ["${CODE_ROOT}/mdtf", "-f","${CODE_ROOT}/src/default_tests.jsonc"]
ENTRYPOINT ["bash","micromamba shell hook --shell bash","micromamba activate _MDTF_base"]
CMD ["/proj/MDTF-diagnostics/mdtf_framework.py", "--help"]
