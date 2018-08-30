Note that instances of dos-azul-lambda deployed as part of the continuous
deployment pipeline configured in [.travis.yml](../.travis.yml) are not
deployed with Chalice and thus will not be deployed with the environment
variables specified in [config.json](config.json) etc. This is a consequence
of using Travis's built-in Lambda deployment provider. To reflect updates to
environment variables made by editing configuration in this directory, you
may need to configure environment variables manually using `awscli` or the
AWS console. (Running `chalice deploy` might actually even be enough.)

In theory, we could add a script to the deployment process outlined in Travis
synchronizing environment variables post-deploy, but that seems to be overkill
for this project, especially when the environment variables generally do not
change. Given that the solution that Chalice recommends is a continuous
deployment pipeline formed by using AWS S3, CodePipeline, etc., this solution,
while it has its shortcomings, seems to be a good compromise between what is
simple and effective.
