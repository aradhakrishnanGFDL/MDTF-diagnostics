# The build-stage image:
FROM continuumio/miniconda3 

# Activate the environment, and make sure it's activated:
ENV CODE_ROOT /proj/MDTF-diagnostics
ENV OBS_DATA_ROOT /inputdata/obs_data/
ENV MODEL_DATA_ROOT /inputdata/model/
ENV PATH /opt/conda/envs/_MDTF_base/bin:$CODE_ROOT:$PATH

#COPY src.mdtf /src/src.mdtf
COPY src $CODE_ROOT/src/
RUN conda env create -f $CODE_ROOT/src/conda/env_base.yml
RUN conda env create -f $CODE_ROOT/src/conda/env_python3_base.yml
RUN conda env create -f $CODE_ROOT/src/conda/env_NCL_base.yml

COPY entrypoint.sh /bin/entrypoint.sh


RUN chmod 777 /bin/entrypoint.sh
#["/bin/bash", "-c", 
ENTRYPOINT ["/bin/entrypoint.sh"]


