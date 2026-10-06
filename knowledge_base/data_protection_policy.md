## FlexiPay India - Data Protection and Storage Policy

### Data localisation
- All payment system data (customer details, transaction records, KYC data) is stored only on servers in India (AWS Mumbai, ap-south-1), in line with RBI's 2018 direction on storage of payment system data.
- Disaster recovery copies are kept in AWS Hyderabad (ap-south-2). No copy is kept outside India.

### Access control
- Production data can be accessed only by named engineers through a bastion host with multi-factor authentication. Every access is logged and the logs are kept for 180 days.
- Customer support staff see masked card and account numbers.

### Retention
- Transaction records are kept for 10 years. Application logs are kept for 1 year.

### Incidents
- A cyber security incident is reported to CERT-In within 6 hours of detection and to the RBI within 24 hours.
- Affected customers are informed within 72 hours where their personal data is involved.

### Vendors
- Vendors who process customer data sign a data processing agreement, must store data in India and are audited once a year.
