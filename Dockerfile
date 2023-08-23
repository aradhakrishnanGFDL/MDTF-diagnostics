# Base OS
FROM ubuntu:latest
FROM continuumio/miniconda3 
# Container Metadata
LABEL maintainer="20195932+wrongkindofdoctor@users.noreply.github.com"
LABEL version="alpha-01"
LABEL description="This is a docker image for the MDTF-diagnostics package"
# Disable Prompt During Packages Installation
ARG DEBIAN_FRONTEND=noninteractive
# Update Ubuntu Software repository
RUN apt update
# Install dependencies
RUN apt install -y wget
RUN apt install -y vim
RUN apt install -y git
# Cleanup
RUN rm -rf /var/lib/apt/lists/* && \
    apt clean
# Install Miniconda3
# Download the latest shell script
####RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
#### Change permission to execute build script
####RUN chmod +x Miniconda3-latest-Linux-x86_64.sh
#### Run miniconda installation script
####ENV PATH="/root/miniconda3/bin:${PATH}"
####ARG PATH="/root/miniconda3/bin:${PATH}"
####RUN bash ./Miniconda3-latest-Linux-x86_64.sh -b
####RUN rm -f Miniconda3-latest-Linux-x86_64.sh
RUN conda info
RUN conda init bash
##RUN conda install 'mamba<=1.4.5' -n base -c conda-forge
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
RUN conda install -c conda-forge -c default libarchive
RUN bash ${CODE_ROOT}/src/conda/conda_env_setup.sh --all --conda_root ${CONDA_ROOT} \
    --env_dir ${CONDA_ENV_DIR}
# Verify installation
RUN ${CODE_ROOT}/mdtf --version
# Run mdtf on src/default_tests.jsonc
CMD ["${CODE_ROOT}/mdtf", "-f","${CODE_ROOT}/src/default_tests.jsonc"]
