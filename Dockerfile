FROM continuumio/miniconda3:master
# Container Metadata
LABEL maintainer="mdtf"
LABEL version="alpha-01"
LABEL description="This is a docker image for the MDTF-diagnostics package"
ARG BUILDKIT_INLINE_CACHE
# Disable Prompt During Packages Installation
#SKIP ARG DEBIAN_FRONTEND=noninteractive
# Update Ubuntu Software repository
#SKIP RUN apt update
# Install dependencies
#SKIP RUN apt install -y wget
#SKIP RUN apt install -y vim
# Cleanup
#SKIP RUN rm -rf /var/lib/apt/lists/* && \
#SKIP     apt clean
# Install Miniconda3
# Download the latest shell script
#SKIP RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
# Change permission to execute build script
#SKIP RUN chmod +x Miniconda3-latest-Linux-x86_64.sh
# Run miniconda installation script
#SKIP ENV PATH="/root/miniconda3/bin:${PATH}"
#SKIP ARG PATH="/root/miniconda3/bin:${PATH}"
#SKIP RUN bash ./Miniconda3-latest-Linux-x86_64.sh -b
#SKIP RUN rm -f Miniconda3-latest-Linux-x86_64.sh
RUN conda info
RUN conda init bash
#testRUN conda install -c conda-forge mamba
# Copy the MDTF-diagnostics package contents from local machine to image
ENV CODE_ROOT=/proj/MDTF-diagnostics
ENV GIT_DIR=.
COPY ${GIT_DIR}/src ${CODE_ROOT}/src
COPY ${GIT_DIR}/data ${CODE_ROOT}/data
COPY ${GIT_DIR}/diagnostics ${CODE_ROOT}/diagnostics
COPY ${GIT_DIR}/mdtf_framework.py ${CODE_ROOT}
COPY ${GIT_DIR}/shared ${CODE_ROOT}/shared
COPY ${GIT_DIR}/sites ${CODE_ROOT}/sites
COPY ${GIT_DIR}/tests ${CODE_ROOT}/tests
# Install conda environments
ENV CONDA_ROOT=/opt/conda/
#ENV CONDA_ENV_DIR=${CONDA_ROOT}/envs
#testRUN bash ${CODE_ROOT}/src/conda/conda_env_setup.sh --all --conda_root ${CONDA_ROOT}
#    --conda_env_dir ${CONDA_ENV_DIR}
# Verify installation

#testCOPY ${GIT_DIR}/entrypoint.sh /bin/entrypoint.sh
#testRUN chmod 777 /bin/entrypoint.sh
#testENTRYPOINT ["/bin/entrypoint.sh"]
