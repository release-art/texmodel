# Security

Report vulnerabilities privately through GitHub's "Report a vulnerability" button on the repository's Security tab,
or by email to ilja@release.art. Please don't open a public issue for them.

texmodel renders TeX from data and can compile it. Treat specs from outside your control as untrusted
(`trust="untrusted"` is the default, plan Z1) and compile them only inside the sandboxed container.
