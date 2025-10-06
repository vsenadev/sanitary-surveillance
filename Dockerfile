# --------------------------------------------------------------------------
# Base: IRIS Community
# --------------------------------------------------------------------------
FROM intersystems/iris-community:latest-cd

# --------------------------------------------------------------------------
# Variáveis de ambiente
# --------------------------------------------------------------------------
ENV APP_HOME=/opt/irisapp \
    APP_LOGS=/opt/irisapp/logs \
    VENV_PATH=/opt/irisapp/venv \
    PYTHONPATH=/opt/irisapp

# --------------------------------------------------------------------------
# Trabalhar como root para preparar diretórios
# --------------------------------------------------------------------------
USER root

WORKDIR $APP_HOME
RUN chown ${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} $APP_HOME

# --------------------------------------------------------------------------
# Copiar scripts e código Python
# --------------------------------------------------------------------------
COPY iris.script $APP_HOME/iris.script
COPY entrypoint.sh $APP_HOME/entrypoint.sh
COPY requirements.txt $APP_HOME/requirements.txt

# Copiar arquivos Python da raiz do projeto
COPY *.py $APP_HOME/

# Permissões
RUN chmod +x $APP_HOME/entrypoint.sh \
    && chown -R ${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} $APP_HOME

# Criar logs
RUN mkdir -p $APP_LOGS \
    && chown -R ${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} $APP_LOGS

# --------------------------------------------------------------------------
# Instalar Python + venv + dependências
# --------------------------------------------------------------------------
RUN python3 -m venv $VENV_PATH \
    && $VENV_PATH/bin/pip install --upgrade pip \
    && $VENV_PATH/bin/pip install -r $APP_HOME/requirements.txt

# --------------------------------------------------------------------------
# Switch para usuário IRIS
# --------------------------------------------------------------------------
USER ${ISC_PACKAGE_MGRUSER}

# --------------------------------------------------------------------------
# Expor portas
# --------------------------------------------------------------------------
EXPOSE 1972 52773 8000 8501

# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------
ENTRYPOINT ["/opt/irisapp/entrypoint.sh"]
