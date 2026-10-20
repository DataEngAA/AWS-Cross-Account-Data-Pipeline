# Definition of done

## Per chunk
A chunk is done when:
- [ ] Everything in the chunk works and its "how to test" step passes
- [ ] Resources are named consistently and tagged (`project`, `account-role`)
- [ ] IAM is least privilege for what was built (no `*` actions without a note)
- [ ] Costly resources created for the lab are stopped or deleted
- [ ] `TASKS.md` updated
- [ ] Notes added to `INTERVIEW_NOTES.md` (what I built, what broke, what I learned)

## Per project
- [ ] AC-01 to AC-09 pass
- [ ] Failure scenarios F-01 to F-05 behave as specified
- [ ] Terraform destroy then apply rebuilds a working pipeline
- [ ] README contains: summary, both diagrams, how to run, cost note, security note
- [ ] Docs in this folder are current (architecture matches what was built)
- [ ] Secret scan clean, Access Analyzer clean, account IDs masked in public material
- [ ] I can explain every cross-account policy in the repo without looking at it
- [ ] All paid resources removed and a final budget check done
