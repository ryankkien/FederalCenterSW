using './main.bicep'

param appLocation = 'eastus'
param postgresLocation = 'centralus'

param appStorageAccountName = 'fcswdevcwm2xrlu'
param appAssetsContainerName = 'app-assets'

param functionStorageAccountName = 'fcswemailfunce7e9f2'
param functionPackageContainerName = 'app-package-fcswemailintakee7e9f2-3009836'
param functionPlanName = 'ASP-federalcenterswdev-818f'
param functionAppName = 'fcsw-email-intake-e7e9f2'

param postgresServerName = 'federal-center-sw-dev-pg-jal50w'
param postgresDatabaseName = 'federal_center_sw'
param postgresAdministratorLogin = 'fcadmin'

param acrName = 'fcswdevacr'
param acaEnvironmentName = 'fcsw-dev-aca-env'
param featureExtractorAppName = 'fcsw-feature-extractor-dev'
// featureExtractorOpenAiApiKey and featureExtractorDatabaseUrl are intentionally not set here; supply via CI/CD secrets or az deployment group create --parameters.
