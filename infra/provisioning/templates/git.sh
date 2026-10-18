# shellcheck shell=bash
# git: from Ubuntu's own archive.
step_git() {
  apt_get install git
  result git 1 "$(git --version | cut -d' ' -f3)" ""
}
