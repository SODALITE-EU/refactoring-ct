pipeline {
  options { disableConcurrentBuilds() }
  agent { label 'docker-slave' }
  stages {
    stage ('Pull repo code from github') {
      steps {
        checkout scm
      }
    }
    stage('test ct-refactoring') {
        steps {
            sh  """ #!/bin/bash 
                    pip3 install -r requirements.txt
                    pip3 install -e .
                    python3 -m pytest --pyargs -s ${WORKSPACE}/tests --junitxml="results.xml" --cov=components/controller --cov-report xml tests/
                """
            junit 'results.xml'
        }
    }
    stage('SonarQube analysis'){
        environment {
          scannerHome = tool 'SonarQubeScanner'
        }
        steps {
            withSonarQubeEnv('SonarCloud') {
                      sh "${scannerHome}/bin/sonar-scanner"
            }
        }
    }
    stage('Build Node Manager actuator') {
            steps {
                sh """#!/bin/bash
                    ./make_docker.sh build node-manager-actuator components/actuator/Dockerfile
                    """
            }
    }
    stage('Build Node Manager containers_manager') {
            steps {
                sh """#!/bin/bash
                    ./make_docker.sh build node-manager-containers_manager components/containers_manager/Dockerfile
                    """
            }
    }
     stage('Build Node Manager requests_store') {
            steps {
                sh """#!/bin/bash
                    ./make_docker.sh build node-manager-requests_store components/requests_store/Dockerfile
                    """
            }
    }
    stage('Build Node Manager controller') {
            steps {
                sh """#!/bin/bash
                    ./make_docker.sh build node-manager-controller components/controller/Dockerfile
                    """
            }
    }
    stage('Build Node Manager dispatcher') {
            steps {
                sh """#!/bin/bash
                    ./make_docker.sh build node-manager-dispatcher components/dispatcher/Dockerfile
                    """
            }
    }
    stage('Push all to sodalite-private-registry') {
            when {
               branch "master"
            }
            steps {
                withDockerRegistry(credentialsId: 'jenkins-sodalite.docker_token', url: '') {
                    sh  """#!/bin/bash
                            ./make_docker.sh push node-manager-actuator production
                            ./make_docker.sh push node-manager-containers_manager production
                            ./make_docker.sh push node-manager-requests_store production
                            ./make_docker.sh push node-manager-controller production
                            ./make_docker.sh push node-manager-dispatcher production
                        """
                }
            }
        }
  }
  post {
    failure {
        slackSend (color: '#FF0000', message: "FAILED: Job '${env.JOB_NAME} [${env.BUILD_NUMBER}]' (${env.BUILD_URL})")
    }
    fixed {
        slackSend (color: '#6d3be3', message: "FIXED: Job '${env.JOB_NAME} [${env.BUILD_NUMBER}]' (${env.BUILD_URL})") 
    }
  }
}
