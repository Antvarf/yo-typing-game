pipeline {
    agent any
    environment {
        HOME = '/root'
    }
    stages {
        stage('Test') {
            steps {
                echo 'Testing'
                sh 'deploy/test.sh'
            }
        }
        stage('Deploy') {
            when {
                expression {
                 currentBuild.result == null || currentBuild.result == 'SUCCESS'
                }
            }
            steps {
                echo 'Deploying'
                sh 'deploy/deploy.sh'
            }
        }
    }
}
